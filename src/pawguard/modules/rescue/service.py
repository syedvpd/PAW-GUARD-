"""RescueService: owns all rescue business behavior (RULE-003)."""

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import (
    DogBreedClassification,
    DogGender,
    DogProfile,
    DogStatus,
)
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.rescue.models import (
    RescueDispatch,
    RescueEscalationType,
    RescuePhysicalCondition,
    RescueReport,
    RescueRequest,
    RescueSeverity,
    RescueStatus,
)
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.schemas import (
    PublicRescueStatusResponse,
    RescueRequestResponse,
    normalise_failure_reason,
)
from pawguard.services.audit_service import AuditService

# Collisions on the 4-digit ticket suffix are rare but possible under high
# intake volume; retry a bounded number of times before giving up cleanly.
_MAX_TICKET_RETRIES = 5


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
    ) -> None:
        self._repo = repository
        self._audit = audit_service
        self._dog_repo = dog_repo

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

        return request

    async def dispatch_team(
        self,
        request_id: uuid.UUID,
        *,
        assigned_driver_id: uuid.UUID | None = None,
        vehicle_id: str | None = None,
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

        dispatch = RescueDispatch(
            rescue_request_id=request_id,
            assigned_driver_id=assigned_driver_id,
            vehicle_id=vehicle_id,
            equipment_details=equipment_details,
            dispatched_at=datetime.now(UTC),
            escalation_type=escalation_type,
            escalation_notes=escalation_notes,
            notes=notes,
        )
        await self._repo.create_dispatch(dispatch)
        # Keep the in-memory relationship consistent: the request was fetched
        # before the dispatch existed, so its `dispatch` attribute is already
        # loaded as None and the re-fetch below would not overwrite it (the
        # identity map preserves the loaded value). Without this, the dispatch
        # response serializes `dispatch: None` even though the row exists.
        request.dispatch = dispatch

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
                    "vehicle_id": vehicle_id,
                    "escalation_type": escalation_type.value if escalation_type else None,
                },
            )

        return res

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
                raise ConflictError("Animal must be in DISPATCHED status to mark LOCATED.")
            dispatch.located_at = now
            request.status = RescueStatus.LOCATED

        elif status == RescueStatus.RESCUED:
            if request.status not in (RescueStatus.DISPATCHED, RescueStatus.LOCATED):
                raise ConflictError(
                    "Animal must be in DISPATCHED or LOCATED status to mark RESCUED."
                )
            dispatch.rescued_at = now
            request.status = RescueStatus.RESCUED

        elif status == RescueStatus.ADMITTED:
            if request.status != RescueStatus.RESCUED:
                raise ConflictError("Animal must be in RESCUED status to mark ADMITTED.")
            dispatch.admitted_at = now
            request.status = RescueStatus.ADMITTED

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

        elif status == RescueStatus.REJECTED:  # representing a failed rescue
            dispatch.failed_at = now
            # Store the canonical PRR 3.3 outcome code; legacy free text and
            # unknown values normalise to the enum (OTHER catch-all).
            dispatch.failure_reason = normalise_failure_reason(failure_reason).value
            request.status = RescueStatus.VERIFIED  # Return back to verified queue

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
            )

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

    async def get_request(self, request_id: uuid.UUID) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")
        return request

    async def lookup_public_status(
        self, ticket_number: str, phone: str
    ) -> PublicRescueStatusResponse:
        """Public "my submitted case" lookup (PRR 3.2).

        Ownership is verified with the ticket number AND the phone the
        reporter submitted with, so guessing a ticket number alone returns
        the same NotFoundError as an invalid one - no case data leaks.
        """
        request = await self._repo.get_request_by_ticket_and_phone(
            ticket_number, phone
        )
        if request is None:
            raise NotFoundError("Rescue request not found.")
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

    async def list_requests_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: RescueStatus | None = None,
        severity: RescueSeverity | None = None,
        urgent_only: bool | None = None,
    ) -> PaginatedResponse[RescueRequestResponse]:
        results, total = await self._repo.list_paginated(
            page=page, sort=sort, search_term=search_term, status=status,
            severity=severity, urgent_only=urgent_only,
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
