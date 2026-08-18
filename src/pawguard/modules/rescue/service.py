"""RescueService: owns all rescue business behavior (RULE-003)."""

import contextlib
import json
import re
import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from logging import getLogger
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from pawguard.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationFailedError,
    parse_enum,
)
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType, AuthAuditLog, Role, User, UserRole
from pawguard.modules.dog.models import (
    DogBreedClassification,
    DogGender,
    DogProfile,
    DogStatus,
)
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.fleet.models import VehicleStatus
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.service import FleetService
from pawguard.modules.rescue.models import (
    RescueDispatch,
    RescueDispatchAgent,
    RescueEscalationType,
    RescueFailureReason,
    RescuePhysicalCondition,
    RescueReport,
    RescueRequest,
    RescueSeverity,
    RescueStatus,
)
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.schemas import (
    PublicRescueStatusResponse,
    RescueDispatchResponse,
    RescueDispatchUpdate,
    RescueEventResponse,
    RescueRequestResponse,
    normalise_failure_reason,
)
from pawguard.redis.client import RedisClient
from pawguard.services.audit_service import AuditService

logger = getLogger(__name__)

# Collisions on the 4-digit ticket suffix are rare but possible under high
# intake volume; retry a bounded number of times before giving up cleanly.
_MAX_TICKET_RETRIES = 5


def _parse_equipment_details(equipment_details: str | None) -> list[str]:
    """Split the dispatch's free-text equipment field into item names.

    Dispatch coordinators enter equipment as a list (newline, comma, or
    semicolon separated); each entry becomes an EquipmentCheckout row.
    """
    if not equipment_details:
        return []
    return [
        name.strip()
        for name in re.split(r"[,;\n]+", equipment_details)
        if name and name.strip()
    ]


def _generate_ticket_number(now: datetime | None = None) -> str:
    """Generate a tracking key like RES-YYYYMMDD-XXXX (PRR 3.2)."""
    now = now or datetime.now(UTC)
    date_str = now.strftime("%Y%m%d")
    rand_suffix = "".join(secrets.choice("0123456789") for _ in range(4))
    return f"RES-{date_str}-{rand_suffix}"


# Statuses reachable via the bulk endpoint, mapped to the current-status
# values each may transition from. REJECTED is intentionally absent: bulk
# rejection is ambiguous (verification rejection needs a rationale, failed
# rescue needs a failure reason) and the bulk payload cannot express either -
# those must go through the single-request verify/fail endpoints.
_BULK_TRANSITION_SOURCES: dict[RescueStatus, set[RescueStatus]] = {
    RescueStatus.VERIFIED: {RescueStatus.REPORTED},
    RescueStatus.DISPATCHED: {RescueStatus.VERIFIED},
    RescueStatus.LOCATED: {RescueStatus.DISPATCHED},
    RescueStatus.RESCUED: {RescueStatus.DISPATCHED, RescueStatus.LOCATED},
    RescueStatus.ADMITTED: {RescueStatus.RESCUED},
}


class RescueService:
    def __init__(
        self,
        repository: RescueRepository,
        audit_service: AuditService | None = None,
        dog_repo: DogRepository | None = None,
        redis_client: RedisClient | None = None,
        arq_pool: Any | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service
        self._dog_repo = dog_repo
        self._redis = redis_client
        self._arq = arq_pool

    async def _send_push(
        self,
        user_ids: list[uuid.UUID],
        title: str,
        body: str,
        action_url: str | None = None,
    ) -> None:
        """Best-effort push notification via the notification service."""
        try:
            from pawguard.modules.notifications.repository import NotificationRepository
            from pawguard.modules.notifications.service import NotificationService

            svc = NotificationService(repository=NotificationRepository(self._repo._session))
            await svc._send_push_to_users(user_ids, title, body, action_url)
        except Exception as exc:
            logger.warning("Failed to send rescue push notification: %s", exc)

    async def _email_reporter(self, *, email: str, subject: str, body: str) -> None:
        """Send only to an existing active PawGuard account."""
        if self._arq is None or not email:
            return
        try:
            registered = await self._repo._session.scalar(
                select(User.id).where(
                    func.lower(User.email) == email.strip().lower(),
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
            if registered is None:
                return
            await self._arq.enqueue_job(
                "send_notification_email_job", to=email, subject=subject, body=body
            )
        except Exception as exc:
            logger.warning("Failed to email rescue reporter %s: %s", email, exc)

    async def _publish_dispatch_event(self) -> None:
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.publish("dispatch:events", "updated")


    def _fleet_service(self) -> FleetService:
        """Cross-domain delegation (fleet) sharing this request's session.

        The dispatch and its equipment checkouts commit atomically: both
        records belong to the same transaction and are flushed together.
        """
        return FleetService(
            repository=FleetRepository(self._repo._session),
            audit_service=self._audit,
        )

    async def report_incident(
        self,
        *,
        reporter_name: str,
        reporter_phone: str,
        reporter_alternate_phone: str | None = None,
        reporter_email: str | None = None,
        is_anonymous: bool = False,
        location_address: str,
        location_landmark: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        animal_count: int = 1,
        physical_condition: RescuePhysicalCondition,
        behavioral_indicators: str | None = None,
        severity: RescueSeverity = RescueSeverity.MEDIUM,
        is_urgent: bool = False,
        media_evidence: list[str] | None = None,
        environmental_factors: str | None = None,
        reporter_notes: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        # Allocate a unique ticket number (RES-YYYYMMDD-XXXX). The 4-digit
        # suffix yields 10k combinations per day, so under heavy intake volume
        # collisions are possible; retry with a fresh suffix rather than
        # letting the unique constraint surface as a 500 (PRR 3.2 tracking key).
        request: RescueRequest | None = None
        for _ in range(_MAX_TICKET_RETRIES):
            ticket_number = _generate_ticket_number()
            # Fast path: skip an already-taken ticket without a DB error.
            if await self._repo.get_request_by_ticket(ticket_number) is not None:
                continue
            candidate = RescueRequest(
                ticket_number=ticket_number,
                reporter_name=reporter_name,
                reporter_phone=reporter_phone,
                reporter_alternate_phone=reporter_alternate_phone,
                reporter_email=reporter_email,
                is_anonymous=is_anonymous,
                location_address=location_address,
                location_landmark=location_landmark,
                latitude=latitude,
                longitude=longitude,
                animal_count=animal_count,
                physical_condition=physical_condition,
                behavioral_indicators=behavioral_indicators,
                severity=severity,
                is_urgent=is_urgent,
                media_evidence=media_evidence,
                environmental_factors=environmental_factors,
                reporter_notes=reporter_notes,
                status=RescueStatus.REPORTED,
            )
            try:
                await self._repo.create_request(candidate)
            except IntegrityError:
                # A concurrent request claimed the same ticket between the
                # existence check and the flush - roll back and try again.
                await self._repo._session.rollback()
                continue
            request = candidate
            break

        if request is None:
            raise ConflictError(
                "Unable to allocate a unique rescue ticket number. Please retry."
            )

        res = await self._repo.get_request_by_id(request.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created rescue request.")

        # Anonymous reports (actor_id=None) MUST still be audited - the public
        # intake is the highest-abuse surface, so the record is written with
        # the reporter's IP even when no user identity is known (PRR §6.1).
        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_REPORTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(res.id),
                    "ticket_number": ticket_number,
                    "is_anonymous": is_anonymous,
                    "media_count": len(media_evidence) if media_evidence else 0,
                },
            )

        await self._publish_dispatch_event()

        # Push notification to rescue coordinators about new incident
        try:
            from pawguard.modules.auth.repository import UserRepository
            user_repo = UserRepository(self._repo._session)
            coordinator_ids = await user_repo.get_user_ids_by_roles(["rescue_coordinator"])
            if coordinator_ids:
                severity_label = "URGENT" if is_urgent else severity.value.upper()
                await self._send_push(
                    coordinator_ids,
                    f"New Rescue Report [{severity_label}]",
                    f"A new animal emergency ({ticket_number}) has been reported at {location_address}.",
                    f"/rescue/{res.id}",
                )
        except Exception as exc:
            logger.warning("Failed to send rescue report push: %s", exc)

        if not is_anonymous and reporter_email:
            await self._email_reporter(
                email=reporter_email,
                subject=f"We received your rescue report {ticket_number}",
                body=(
                    f"Thank you for reporting an animal emergency. Our rescue "
                    f"team has received your report ({ticket_number}) and will "
                    "review it shortly. You can track its status on the PawGuard "
                    "portal using the ticket number."
                ),
            )
        return res


    async def verify_request(
        self,
        request_id: uuid.UUID,
        *,
        approve: bool,
        rationale: str | None = None,
        severity: RescueSeverity | None = None,
        is_urgent: bool | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")

        if request.status != RescueStatus.REPORTED:
            raise ConflictError(f"Cannot verify request in status: {request.status}")

        # Coordinator severity prioritization at verification (PRR 3.2):
        # refine the reporter's self-assessed severity / urgent flag even when
        # the case is being approved.
        if severity is not None:
            request.severity = severity
        if is_urgent is not None:
            request.is_urgent = is_urgent

        if approve:
            request.status = RescueStatus.VERIFIED
        else:
            if not rationale or not rationale.strip():
                raise ValidationFailedError(
                    "A rejection rationale is required when rejecting a rescue request."
                )
            request.status = RescueStatus.REJECTED
            request.rejection_rationale = rationale

        await self._repo._session.flush()
        await self._repo._session.refresh(request)

        if self._audit and actor_id:
            event = (
                AuthAuditEventType.RESCUE_VERIFIED if approve
                else AuthAuditEventType.RESCUE_REJECTED
            )
            await self._audit.record(
                event_type=event,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "new_status": str(request.status),
                    "rationale": rationale,
                    "severity": str(request.severity),
                    "is_urgent": request.is_urgent,
                },
            )

        await self._publish_dispatch_event()
        return request


    async def dispatch_team(
        self,
        request_id: uuid.UUID,
        *,
        assigned_driver_id: uuid.UUID | None = None,
        assigned_agent_ids: list[uuid.UUID] | None = None,
        vehicle_id: str | None = None,
        assigned_vehicle_id: uuid.UUID | None = None,
        equipment_details: str | None = None,
        escalation_type: RescueEscalationType | None = None,
        escalation_notes: str | None = None,
        notes: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")

        if request.status != RescueStatus.VERIFIED:
            raise ConflictError(f"Cannot dispatch for request in status: {request.status}")

        # Check if already has active dispatch
        existing_dispatch = await self._repo.get_dispatch_by_request_id(request_id)
        if existing_dispatch is not None:
            raise ConflictError("Dispatch record already exists for this request.")

        # Vehicle assignment (PRR 3.2): the vehicle must exist and be ACTIVE.
        # Delegates existence lookup to the fleet domain and enforces the
        # operational rule here in the service layer.
        if assigned_vehicle_id is not None:
            vehicle = await self._fleet_service().get_vehicle(assigned_vehicle_id)
            if vehicle.status != VehicleStatus.ACTIVE:
                raise ValidationFailedError(
                    "Only ACTIVE vehicles can be assigned to a rescue dispatch "
                    f"(vehicle is '{vehicle.status.value}')."
                )

        if assigned_driver_id is not None and not await self._repo.user_exists(assigned_driver_id):
            raise NotFoundError(f"Assigned driver user '{assigned_driver_id}' not found.")

        # Assemble the full team: the explicit agent list plus the legacy
        # single-driver field, deduplicated. Every member is mirrored into
        # the dispatch-agent association table so "one or more agents" holds
        # for both the new multi-agent flow and the back-compat driver flow.
        agent_ids: list[uuid.UUID] = []
        for agent_id in assigned_agent_ids or []:
            if not await self._repo.user_exists(agent_id):
                raise NotFoundError(f"Assigned agent user '{agent_id}' not found.")
            if agent_id not in agent_ids:
                agent_ids.append(agent_id)
        if assigned_driver_id is not None and assigned_driver_id not in agent_ids:
            agent_ids.append(assigned_driver_id)

        dispatch = RescueDispatch(
            rescue_request_id=request_id,
            assigned_driver_id=assigned_driver_id,
            vehicle_id=vehicle_id,
            assigned_vehicle_id=assigned_vehicle_id,
            equipment_details=equipment_details,
            dispatched_at=datetime.now(UTC),
            escalation_type=escalation_type,
            escalation_notes=escalation_notes,
            notes=notes,
        )
        try:
            await self._repo.create_dispatch(dispatch)
            for agent_id in agent_ids:
                await self._repo.create_dispatch_agent(
                    RescueDispatchAgent(dispatch_id=dispatch.id, agent_id=agent_id)
                )
        except IntegrityError as exc:
            raise ValidationFailedError(
                "Failed to create dispatch record due to database constraint violation."
            ) from exc

        # Keep the in-memory relationship consistent: the request was fetched
        # before the dispatch existed, so its `dispatch` attribute is already
        # loaded as None and the re-fetch below would not overwrite it (the
        # identity map preserves the loaded value). Without this, the dispatch
        # response serializes `dispatch: None` even though the row exists.
        request.dispatch = dispatch

        # Auto-checkout the equipment named on the dispatch (PRR 3.3) so the
        # fleet ledger tracks what left the shelter for this rescue. Uses the
        # shared session, so it commits atomically with the dispatch.
        equipment_names = _parse_equipment_details(equipment_details)
        if equipment_names:
            await self._fleet_service().checkout_equipment_for_dispatch(
                rescue_dispatch_id=dispatch.id,
                equipment_names=equipment_names,
                assigned_to_agent_id=assigned_driver_id,
                assigned_to_vehicle_id=None,
                actor_id=actor_id,
                ip_address=ip_address,
            )

        request.status = RescueStatus.DISPATCHED
        await self._repo._session.flush()
        res = await self._repo.get_request_by_id(request_id)
        if res is None:
            raise NotFoundError("Rescue request not found after dispatch.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_DISPATCHED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "assigned_driver_id": str(assigned_driver_id) if assigned_driver_id else None,
                    "assigned_agent_ids": [str(i) for i in agent_ids],
                    "vehicle_id": vehicle_id,
                    "assigned_vehicle_id": (
                        str(assigned_vehicle_id) if assigned_vehicle_id else None
                    ),
                    "escalation_type": escalation_type.value if escalation_type else None,
                },
            )

        await self._publish_dispatch_event()

        # Push notification to assigned agents about new dispatch
        if agent_ids:
            try:
                await self._send_push(
                    agent_ids,
                    "New Rescue Dispatch Assignment",
                    f"You have been assigned to rescue case {request.ticket_number}. Please mobilize immediately.",
                    f"/rescue/{request_id}",
                )
            except Exception as exc:
                logger.warning("Failed to send dispatch push: %s", exc)

        return res

    async def update_dispatch(
        self,
        dispatch_id: uuid.UUID,
        payload: RescueDispatchUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueDispatch:
        dispatch = await self._repo.get_dispatch_by_id(dispatch_id)
        if dispatch is None:
            dispatch = await self._repo.get_dispatch_by_request_id(dispatch_id)
        if dispatch is None:
            raise NotFoundError("Rescue dispatch record not found.")

        if payload.assigned_driver_id is not None:
            dispatch.assigned_driver_id = payload.assigned_driver_id
        if payload.vehicle_id is not None:
            dispatch.vehicle_id = payload.vehicle_id
        if payload.assigned_vehicle_id is not None:
            dispatch.assigned_vehicle_id = payload.assigned_vehicle_id
        if payload.equipment_details is not None:
            dispatch.equipment_details = payload.equipment_details
        if payload.notes is not None:
            dispatch.notes = payload.notes
        if payload.escalation_notes is not None:
            dispatch.escalation_notes = payload.escalation_notes
        if payload.escalation_type is not None:
            dispatch.escalation_type = parse_enum(RescueEscalationType, payload.escalation_type)
        if payload.failure_reason is not None:
            dispatch.failure_reason = parse_enum(RescueFailureReason, payload.failure_reason)
        if payload.located_at is not None:
            dispatch.located_at = payload.located_at
        if payload.rescued_at is not None:
            dispatch.rescued_at = payload.rescued_at
        if payload.admitted_at is not None:
            dispatch.admitted_at = payload.admitted_at
        if payload.failed_at is not None:
            dispatch.failed_at = payload.failed_at

        await self._repo._session.flush()
        await self._repo._session.refresh(dispatch, attribute_names=["updated_at"])
        return dispatch

    async def delete_dispatch(
        self,
        dispatch_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        dispatch = await self._repo.get_dispatch_by_id(dispatch_id)
        if dispatch is None:
            dispatch = await self._repo.get_dispatch_by_request_id(dispatch_id)
        if dispatch is None:
            raise NotFoundError("Rescue dispatch record not found.")

        await self._repo.delete_dispatch(dispatch)


    async def escalate(
        self,
        request_id: uuid.UUID,
        *,
        escalation_type: RescueEscalationType,
        escalation_notes: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")

        dispatch = await self._repo.get_dispatch_by_request_id(request_id)
        if dispatch is None:
            raise NotFoundError("Dispatch record not found for this request.")

        dispatch.escalation_type = escalation_type
        dispatch.escalation_notes = escalation_notes
        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_DISPATCHED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "escalation_type": escalation_type.value,
                    "escalation_notes": escalation_notes,
                },
            )

        res = await self._repo.get_request_by_id(request_id)
        if res is None:
            raise NotFoundError("Rescue request not found after escalation.")

        # Push notification to admins about escalation
        try:
            from pawguard.modules.auth.repository import UserRepository
            user_repo = UserRepository(self._repo._session)
            admin_ids = await user_repo.get_user_ids_by_roles(["rescue_centre_admin", "super_admin"])
            if admin_ids:
                await self._send_push(
                    admin_ids,
                    f"Rescue Escalation: {escalation_type.value}",
                    f"Rescue case {request.ticket_number} has been escalated. Notes: {escalation_notes or 'None'}",
                    f"/rescue/{request_id}",
                )
        except Exception as exc:
            logger.warning("Failed to send escalation push: %s", exc)

        return res

    async def accept_dispatch(
        self,
        request_id: uuid.UUID,
        *,
        agent_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")

        dispatch = await self._repo.get_dispatch_by_request_id(request_id)
        if dispatch is None:
            raise NotFoundError("Dispatch record not found for this request.")

        # Ensure the agent is assigned to this dispatch
        is_assigned = False
        if dispatch.assigned_driver_id == agent_id:
            is_assigned = True
        else:
            for agent in dispatch.agents:
                if agent.agent_id == agent_id:
                    is_assigned = True
                    break
        
        if not is_assigned:
            raise ConflictError("Agent is not assigned to this dispatch.")

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_STATUS_UPDATED,
                actor_id=agent_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "action": "dispatch_accepted",
                },
            )

        return request

    async def add_observation_report(
        self,
        request_id: uuid.UUID,
        *,
        agent_id: uuid.UUID,
        notes: str | None = None,
        photos: list[str] | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")

        report = RescueReport(
            rescue_request_id=request_id,
            agent_id=agent_id,
            notes=notes,
            photos=photos,
        )
        await self._repo.create_report(report)
        request.reports.append(report)

        await self._repo._session.flush()

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_STATUS_UPDATED,
                actor_id=agent_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "action": "observation_report_added",
                    "media_count": len(photos) if photos else 0,
                },
            )

        return request

    async def update_dispatch_status(
        self,
        request_id: uuid.UUID,
        *,
        status: RescueStatus,
        agent_id: uuid.UUID,
        notes: str | None = None,
        photos: list[str] | None = None,
        failure_reason: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")

        dispatch = await self._repo.get_dispatch_by_request_id(request_id)
        if dispatch is None:
            raise NotFoundError("Dispatch record not found for this request.")

        old_status = request.status
        now = datetime.now(UTC)

        if status == RescueStatus.LOCATED:
            if request.status != RescueStatus.DISPATCHED:
                raise ValidationFailedError("Animal must be in DISPATCHED status to mark LOCATED.")
            dispatch.located_at = now
            request.status = RescueStatus.LOCATED

        elif status == RescueStatus.RESCUED:
            if request.status not in (RescueStatus.DISPATCHED, RescueStatus.LOCATED):
                raise ValidationFailedError(
                    "Animal must be in DISPATCHED or LOCATED status to mark RESCUED."
                )
            dispatch.rescued_at = now
            request.status = RescueStatus.RESCUED

        elif status == RescueStatus.ADMITTED:
            if request.status != RescueStatus.RESCUED:
                raise ValidationFailedError("Animal must be in RESCUED status to mark ADMITTED.")
            dispatch.admitted_at = now
            request.status = RescueStatus.ADMITTED

            # Release equipment checked out for this dispatch (PRR 3.3): the
            # rescue is complete, so nothing should remain outstanding.
            await self._fleet_service().release_equipment_for_dispatch(
                rescue_dispatch_id=dispatch.id,
                actor_id=agent_id,
                ip_address=ip_address,
            )

            # Create internal report
            report = RescueReport(
                rescue_request_id=request_id,
                agent_id=agent_id,
                notes=notes,
                photos=photos,
            )
            await self._repo.create_report(report)
            request.reports.append(report)

            # ADMITTED must create the internal Dog Profile automatically
            # (PRR 3.2) rather than relying on staff to remember a separate
            # POST /dogs call.
            if self._dog_repo is not None:
                await self._create_dog_profile_for_admitted(
                    request, now=now, actor_id=actor_id, ip_address=ip_address
                )

            # Push notification to veterinarians about new intake
            try:
                from pawguard.modules.auth.repository import UserRepository
                user_repo = UserRepository(self._repo._session)
                vet_ids = await user_repo.get_user_ids_by_roles(["veterinarian"])
                if vet_ids:
                    await self._send_push(
                        vet_ids,
                        "New Animal Admitted",
                        f"Animal from case {request.ticket_number} has been admitted and requires intake examination.",
                        f"/rescue/{request_id}",
                    )
            except Exception as exc:
                logger.warning("Failed to send admission push: %s", exc)

        elif status == RescueStatus.REJECTED:  # representing a failed rescue
            dispatch.failed_at = now
            # Store the canonical PRR 3.3 outcome code; legacy free text and
            # unknown values normalise to the enum (OTHER catch-all).
            dispatch.failure_reason = normalise_failure_reason(failure_reason).value
            # A failed rescue is closed, not re-queued for verification.
            request.status = RescueStatus.REJECTED

            # Release equipment checked out for the aborted dispatch (PRR 3.3).
            await self._fleet_service().release_equipment_for_dispatch(
                rescue_dispatch_id=dispatch.id,
                actor_id=agent_id,
                ip_address=ip_address,
            )

        else:
            raise ConflictError(f"Unsupported status update: {status}")

        await self._repo._session.flush()
        res = await self._repo.get_request_by_id(request_id)
        if res is None:
            raise NotFoundError("Rescue request not found after status update.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "old_status": str(old_status),
                    "new_status": str(request.status),
                    "requested_status": status.value,
                    "failure_reason": failure_reason,
                },
                # Structured before/after snapshots (audit finding #3).
                before_state={"status": str(old_status)},
                after_state={"status": str(request.status)},
            )

        await self._publish_dispatch_event()
        return res


    async def _create_dog_profile_for_admitted(
        self,
        request: RescueRequest,
        *,
        now: datetime,
        actor_id: uuid.UUID | None,
        ip_address: str | None,
    ) -> None:
        """Auto-create the internal Dog Profile when a rescue is ADMITTED
        (PRR 3.2). Shared by the single-request admit path and the bulk path
        so both produce the same profile and audit trail."""
        if self._dog_repo is None:
            return
        year_str = now.strftime("%Y")
        rand_suffix = "".join(secrets.choice("0123456789") for _ in range(4))
        dog = DogProfile(
            registration_number=f"DOG-{year_str}-{rand_suffix}",
            rescue_case_id=request.id,
            name=f"Unnamed ({request.ticket_number})",
            breed="indie_mix",
            breed_classification=DogBreedClassification.MIX,
            gender=DogGender.UNKNOWN,
            status=DogStatus.RESCUED,
            is_adoptable=False,
        )
        await self._dog_repo.create(dog)
        # Attach the newly created profile to the in-session request so the
        # admit response can surface its id. The `dog_profile` relationship is
        # viewonly, and the subsequent re-fetch returns the same identity-mapped
        # instance, so we set it explicitly here.
        request.dog_profile = dog
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DOG_REGISTERED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "dog_id": str(dog.id),
                    "registration_number": dog.registration_number,
                    "rescue_id": str(request.id),
                    "auto_created": True,
                },
            )

        if self._redis is not None:
            with contextlib.suppress(Exception):
                keys = [
                    "pawguard:hero_stats",
                    "pawguard:transparency_stats",
                    "hero_stats",
                    "transparency_stats",
                    "cache:dashboard:shelter",
                    "cache:dashboard:rescue",
                    "cache:dashboard:adoption",
                    "cache:dashboard:summary",
                ]
                for key in keys:
                    await self._redis.delete(key)

    async def get_request(self, request_id: uuid.UUID) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")
        return request

    async def assign_coordinator(
        self,
        request_id: uuid.UUID,
        coordinator_id: uuid.UUID,
        notes: str | None = None,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        """Assign a coordinator to a rescue case and notify them (PRR 3.2)."""
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")

        # Validate the coordinator user exists and is active.
        from sqlalchemy import select as sa_select

        from pawguard.modules.auth.models import User
        user = await self._repo._session.scalar(
            sa_select(User.id).where(
                User.id == coordinator_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if user is None:
            raise NotFoundError("Coordinator user not found or inactive.")

        request.coordinator_id = coordinator_id
        await self._repo._session.flush()
        await self._repo._session.refresh(request, attribute_names=["updated_at"])

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_COORDINATOR_ASSIGNED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "coordinator_id": str(coordinator_id),
                    "notes": notes,
                },
            )

        return request

    async def lookup_public_status(
        self, ticket_number: str, phone: str
    ) -> PublicRescueStatusResponse | None:
        """Public "my submitted case" lookup (PRR 3.2).

        Ownership is verified with the ticket number AND the phone the
        reporter submitted with, so guessing a ticket number alone returns
        the same NotFoundError as an invalid one - no case data leaks.

        Returns None when no match is found (instead of raising 404), so the
        router can return HTTP 200 with an empty payload — matching the
        documented contract.
        """
        request = await self._repo.get_request_by_ticket_and_phone(
            ticket_number, phone
        )
        if request is None:
            return None
        return PublicRescueStatusResponse(
            ticket_number=request.ticket_number,
            status=request.status,
            severity=request.severity,
            animal_count=request.animal_count,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )

    async def list_requests(self, status: RescueStatus | None = None) -> Sequence[RescueRequest]:
        return await self._repo.list_requests(status)

    async def list_dispatches_paginated(
        self, page: PageParams, sort: SortParams
    ) -> PaginatedResponse[RescueDispatchResponse]:
        dispatches, total = await self._repo.list_dispatches_paginated(
            page=page, sort=sort
        )
        return PaginatedResponse(
            data=[RescueDispatchResponse.model_validate(d) for d in dispatches],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def list_requests_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: RescueStatus | None = None,
        severity: RescueSeverity | None = None,
        urgent_only: bool | None = None,
        assigned_to_me: uuid.UUID | None = None,
    ) -> PaginatedResponse[RescueRequestResponse]:
        results, total = await self._repo.list_paginated(
            page=page, sort=sort, search_term=search_term, status=status,
            severity=severity, urgent_only=urgent_only,
            assigned_to_me=assigned_to_me,
        )
        return PaginatedResponse(
            data=[RescueRequestResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def soft_delete_request(
        self,
        request_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")
        request.deleted_at = datetime.now(UTC)

        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"rescue_id": str(request_id), "ticket_number": request.ticket_number},
            )

    async def bulk_update_status(
        self,
        ids: list[uuid.UUID],
        status: RescueStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        """Bulk status update with state-machine enforcement.

        The whole batch is validated against the legal transition table
        before anything is applied (all-or-nothing): if any request is in a
        state that cannot reach the target status, the batch is rejected and
        nothing changes - this closes the hole where a bare UPDATE could jump
        e.g. REPORTED -> ADMITTED. ADMITTED performs the same side effects as
        the single-request path (field report + auto-created DogProfile).
        REJECTED is not bulk-applicable: rejection requires a per-request
        rationale/failure reason the bulk payload cannot express (PRR 3.2).
        """
        if status == RescueStatus.REJECTED:
            raise ValidationFailedError(
                "Bulk REJECTED is not supported: rejection requires a "
                "per-request rationale (verification) or failure reason "
                "(failed rescue). Use the single-request verify/fail "
                "endpoints instead."
            )
        allowed_sources = _BULK_TRANSITION_SOURCES.get(status)
        if allowed_sources is None:
            raise ValidationFailedError(
                f"Bulk status '{status.value}' is not supported."
            )

        requests = await self._repo.list_by_ids(ids)
        if not requests:
            raise NotFoundError("No rescue requests found for the given ids.")

        invalid = [r.ticket_number for r in requests if r.status not in allowed_sources]
        if invalid:
            raise ConflictError(
                f"Cannot bulk-set status to '{status.value}': request(s) "
                f"{', '.join(invalid)} are not in a state that allows this "
                f"transition (allowed from: "
                f"{sorted(s.value for s in allowed_sources)})."
            )

        now = datetime.now(UTC)
        for request in requests:
            request.status = status

            if status == RescueStatus.VERIFIED:
                # Pure state change - no dispatch exists yet.
                pass
            elif status == RescueStatus.DISPATCHED:
                existing = request.dispatch
                if existing is None:
                    await self._repo.create_dispatch(
                        RescueDispatch(
                            rescue_request_id=request.id, dispatched_at=now
                        )
                    )
            elif status in (RescueStatus.LOCATED, RescueStatus.RESCUED, RescueStatus.ADMITTED):
                dispatch = request.dispatch
                if dispatch is None:
                    raise NotFoundError(
                        f"Dispatch record not found for request "
                        f"{request.ticket_number}."
                    )
                if status == RescueStatus.LOCATED:
                    dispatch.located_at = now
                elif status == RescueStatus.RESCUED:
                    dispatch.rescued_at = now
                elif status == RescueStatus.ADMITTED:
                    dispatch.admitted_at = now
                    report = RescueReport(
                        rescue_request_id=request.id, agent_id=actor_id
                    )
                    await self._repo.create_report(report)
                    request.reports.append(report)
                    await self._create_dog_profile_for_admitted(
                        request, now=now, actor_id=actor_id, ip_address=ip_address
                    )

        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.BULK_RESCUE_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_ids": [str(i) for i in ids],
                    "status": status.value,
                    "count": len(requests),
                },
            )

        return len(requests)

    async def bulk_soft_delete(
        self,
        ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_soft_delete(ids)

        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.BULK_RESCUE_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"rescue_ids": [str(i) for i in ids], "count": count},
            )

        return count

    async def update_agent_location(
        self,
        agent_id: uuid.UUID,
        latitude: float,
        longitude: float,
    ) -> None:
        """Update an agent's current coordinates in Redis with a heartbeat TTL (PRR 3.2)."""
        key = "rescue:agent_locations"
        active_key = f"rescue:agent_active:{agent_id}"

        # 1. Update geolocation set
        await self._redis.geoadd(key, (longitude, latitude, str(agent_id)))
        # 2. Set liveness/active status heartbeat (5 minutes TTL)
        await self._redis.set(active_key, "1", ex=300)
        # 3. Store timestamp for location retrieval endpoints
        with contextlib.suppress(Exception):
            await self._redis.set(
                f"rescue:agent_ts:{agent_id}", datetime.now(UTC).isoformat()
            )

    async def get_nearest_agents(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
    ) -> list[dict[str, Any]]:
        """Suggest nearest active agents within radius_km (PRR 3.2).

        Queries the Redis geo-index, filters for active heartbeats, and retrieves
        matching user details from the database. Falls back to listing all active
        rescue agents if Redis is empty/unconfigured.
        """
        key = "rescue:agent_locations"
        nearby_agents = []

        try:
            # Query Redis for members within radius
            # redis-py geosearch returns [[member, distance, (lng, lat)], ...]
            raw_results = await self._redis.geosearch(
                key,
                longitude=longitude,
                latitude=latitude,
                radius=radius_km,
                unit="km",
                withdist=True,
                withcoord=True,
            )
        except Exception as exc:
            logger.warning("Redis geosearch failed, using DB fallback: %s", exc)
            raw_results = []

        # Parse geosearch results: [[agent_id, distance_km, (lng, lat)], ...]
        agent_geo_data = {}
        for res in raw_results:
            if isinstance(res, (list, tuple)) and len(res) >= 3:
                member_id_str, dist, coord = res[0], res[1], res[2]
            else:
                continue
            
            try:
                member_uuid = uuid.UUID(member_id_str)
            except ValueError:
                continue

            # Check heartbeat liveness
            active = await self._redis.get(f"rescue:agent_active:{member_id_str}")
            if active:
                agent_geo_data[member_uuid] = {
                    "distance_km": float(dist),
                    "longitude": float(coord[0]) if coord else None,
                    "latitude": float(coord[1]) if coord else None,
                }

        # Query users from the DB — filter by rescue roles to avoid
        # surfacing non-rescue users (finance, vets, etc.) in suggestions.
        if agent_geo_data:
            from pawguard.modules.auth.models import Role, UserRole
            stmt = (
                select(User)
                .options(selectinload(User.roles))
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    User.id.in_(agent_geo_data.keys()),
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    Role.name.in_(["rescue_agent", "rescue_coordinator"]),
                )
                .distinct()
            )
            users = (await self._repo._session.execute(stmt)).scalars().all()
            for user in users:
                geo = agent_geo_data[user.id]
                nearby_agents.append({
                    "agent_id": user.id,
                    "name": user.full_name,
                    "email": user.email,
                    "phone": user.phone,
                    "distance_km": geo["distance_km"],
                    "latitude": geo["latitude"],
                    "longitude": geo["longitude"],
                })
            # Sort by distance
            nearby_agents.sort(key=lambda x: x["distance_km"] or 0.0)

        # Fallback: if no active agents found in Redis, list all active rescue agents from DB
        if not nearby_agents:
            from pawguard.modules.auth.models import Role, UserRole
            stmt = (
                select(User)
                .options(selectinload(User.roles))
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                    Role.name.in_(["rescue_agent", "rescue_coordinator", "super_admin"]),
                )
                .distinct()
            )
            fallback_users = (await self._repo._session.execute(stmt)).scalars().all()
            for user in fallback_users:
                nearby_agents.append({
                    "agent_id": user.id,
                    "name": user.full_name,
                    "email": user.email,
                    "phone": user.phone,
                    "distance_km": None,
                    "latitude": None,
                    "longitude": None,
                })

        return nearby_agents

    # ── Availability (PRR 3.2 coordinator resource selection) ──────────────

    async def get_agent_availability(self) -> list[dict[str, Any]]:
        """List rescue agents with dynamic availability derived from active dispatches."""
        session = self._repo._session
        active_statuses = [
            RescueStatus.DISPATCHED, RescueStatus.LOCATED, RescueStatus.RESCUED,
        ]
        # Agents currently on an in-progress dispatch are "busy".
        busy_stmt = (
            select(RescueDispatchAgent.agent_id, RescueDispatch.id.label("dispatch_id"))
            .join(RescueDispatch, RescueDispatch.id == RescueDispatchAgent.dispatch_id)
            .join(RescueRequest, RescueRequest.id == RescueDispatch.rescue_request_id)
            .where(
                RescueRequest.status.in_(active_statuses),
                RescueRequest.deleted_at.is_(None),
            )
        )
        busy_map: dict[uuid.UUID, uuid.UUID] = {}
        for row in (await session.execute(busy_stmt)).all():
            busy_map[row[0]] = row[1]

        # All active rescue agents.
        agents_stmt = (
            select(User)
            .options(selectinload(User.roles))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                Role.name == "rescue_agent",
            )
        )
        agents = (await session.execute(agents_stmt)).scalars().all()

        result = []
        for agent in agents:
            is_busy = agent.id in busy_map
            lat = lng = heartbeat = None
            if self._redis is not None:
                with contextlib.suppress(Exception):
                    geo = await self._redis.geopos("rescue:agent_locations", str(agent.id))
                    if geo and geo[0]:
                        lng, lat = float(geo[0][0]), float(geo[0][1])
                    hb = await self._redis.get(f"rescue:agent_active:{agent.id}")
                    heartbeat = "active" if hb else None
            result.append({
                "agent_id": agent.id,
                "name": agent.full_name,
                "status": "busy" if is_busy else "available",
                "active_dispatch_id": busy_map.get(agent.id),
                "last_heartbeat": heartbeat,
                "latitude": lat,
                "longitude": lng,
            })
        return result

    async def get_vehicle_availability(self) -> list[dict[str, Any]]:
        """List fleet vehicles with availability derived from active dispatches."""
        session = self._repo._session
        active_statuses = [
            RescueStatus.DISPATCHED, RescueStatus.LOCATED, RescueStatus.RESCUED,
        ]
        # Vehicles currently assigned to an in-progress dispatch.
        assigned_stmt = (
            select(
                RescueDispatch.assigned_vehicle_id,
                RescueDispatch.id.label("dispatch_id"),
            )
            .join(RescueRequest, RescueRequest.id == RescueDispatch.rescue_request_id)
            .where(
                RescueDispatch.assigned_vehicle_id.isnot(None),
                RescueRequest.status.in_(active_statuses),
                RescueRequest.deleted_at.is_(None),
            )
        )
        assigned_map: dict[uuid.UUID, uuid.UUID] = {}
        for row in (await session.execute(assigned_stmt)).all():
            assigned_map[row[0]] = row[1]

        fleet_repo = FleetRepository(session)
        vehicles = await fleet_repo.list_all_vehicles()

        result = []
        for v in vehicles:
            if v.status == VehicleStatus.OUT_OF_SERVICE:
                availability = "out_of_service"
            elif v.status == VehicleStatus.IN_MAINTENANCE:
                availability = "maintenance"
            elif v.id in assigned_map:
                availability = "assigned"
            else:
                availability = "available"
            result.append({
                "vehicle_id": v.id,
                "license_plate": v.license_plate,
                "vehicle_type": v.vehicle_type.value if v.vehicle_type else None,
                "operational_status": v.status.value,
                "availability": availability,
                "active_dispatch_id": assigned_map.get(v.id),
            })
        return result

    # ── GPS Tracking Lifecycle (PRR 3.2) ──────────────────────────────────

    async def _get_tracking_state(self, request_id: uuid.UUID) -> dict[str, Any]:
        default: dict[str, Any] = {"active": False, "started_at": None, "stopped_at": None}
        if self._redis is None:
            return default
        with contextlib.suppress(Exception):
            raw = await self._redis.get(f"rescue:tracking:{request_id}")
            if raw:
                data = json.loads(raw)
                data.setdefault("active", False)
                return data
        return default

    async def _set_tracking_state(
        self, request_id: uuid.UUID, state: dict[str, Any]
    ) -> None:
        if self._redis is None:
            return
        with contextlib.suppress(Exception):
            await self._redis.set(
                f"rescue:tracking:{request_id}", json.dumps(state)
            )

    async def start_tracking(
        self,
        request_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        dispatch = await self._repo.get_dispatch_by_request_id(request_id)
        if dispatch is None:
            raise NotFoundError("No dispatch exists for this rescue request.")
        state = await self._get_tracking_state(request_id)
        state["active"] = True
        state["started_at"] = datetime.now(UTC).isoformat()
        await self._set_tracking_state(request_id, state)
        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "action": "tracking_started",
                },
            )
        return state

    async def stop_tracking(
        self,
        request_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        dispatch = await self._repo.get_dispatch_by_request_id(request_id)
        if dispatch is None:
            raise NotFoundError("No dispatch exists for this rescue request.")
        state = await self._get_tracking_state(request_id)
        state["active"] = False
        state["stopped_at"] = datetime.now(UTC).isoformat()
        await self._set_tracking_state(request_id, state)
        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(request_id),
                    "action": "tracking_stopped",
                },
            )
        return state

    async def get_tracking_status(
        self, request_id: uuid.UUID
    ) -> dict[str, Any]:
        return await self._get_tracking_state(request_id)

    async def get_rescue_location(
        self, request_id: uuid.UUID
    ) -> dict[str, Any]:
        """Return latest GPS positions for all agents assigned to a rescue dispatch."""
        dispatch = await self._repo.get_dispatch_by_request_id(request_id)
        if dispatch is None:
            raise NotFoundError("No dispatch exists for this rescue request.")

        agent_ids: list[uuid.UUID] = [a.agent_id for a in dispatch.agents]
        if dispatch.assigned_driver_id is not None:
            agent_ids.append(dispatch.assigned_driver_id)

        agents_out: list[dict[str, Any]] = []
        updated_at: str | None = None
        for aid in agent_ids:
            lat = lng = heartbeat = ts = None
            if self._redis is not None:
                with contextlib.suppress(Exception):
                    geo = await self._redis.geopos("rescue:agent_locations", str(aid))
                    if geo and geo[0]:
                        lng, lat = float(geo[0][0]), float(geo[0][1])
                    hb = await self._redis.get(f"rescue:agent_active:{aid}")
                    heartbeat = "active" if hb else None
                    ts_raw = await self._redis.get(f"rescue:agent_ts:{aid}")
                    ts = ts_raw if isinstance(ts_raw, str) else None
            agents_out.append({
                "agent_id": aid,
                "latitude": lat,
                "longitude": lng,
                "last_heartbeat": heartbeat,
                "updated_at": ts,
            })
            if ts and (updated_at is None or ts > updated_at):
                updated_at = ts

        return {
            "request_id": str(request_id),
            "agents": agents_out,
            "vehicle": None,
            "updated_at": updated_at,
        }

    # ── Rescue Event Feed (PRR 3.2 audit trail) ────────────────────────────

    async def get_rescue_events(
        self,
        request_id: uuid.UUID,
        page: PageParams,
    ) -> PaginatedResponse[RescueEventResponse]:
        """Return rescue-related audit events for a specific case."""
        session = self._repo._session
        stmt = (
            select(AuthAuditLog)
            .where(
                AuthAuditLog.event_metadata["rescue_id"].astext == str(request_id),
                AuthAuditLog.event_type.like("rescue_%"),
            )
            .order_by(AuthAuditLog.created_at.desc())
        )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        rows = (await session.execute(stmt)).scalars().all()

        data = [
            RescueEventResponse(
                event_type=r.event_type,
                actor_id=r.user_id,
                created_at=r.created_at.isoformat(),
                metadata=r.event_metadata,
            )
            for r in rows
        ]
        return PaginatedResponse(
            data=data,
            meta=build_pagination_meta(total=total, params=page),
        )

