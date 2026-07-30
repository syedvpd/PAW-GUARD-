"""RescueService: owns all rescue business behavior (RULE-003)."""

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.rescue.models import RescueDispatch, RescueReport, RescueRequest, RescueStatus
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.schemas import RescueRequestResponse
from pawguard.services.audit_service import AuditService


class RescueService:
    def __init__(
        self, repository: RescueRepository, audit_service: AuditService | None = None
    ) -> None:
        self._repo = repository
        self._audit = audit_service

    async def report_incident(
        self,
        *,
        reporter_name: str,
        reporter_phone: str,
        reporter_email: str | None = None,
        is_anonymous: bool = False,
        location_address: str,
        location_landmark: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        animal_count: int = 1,
        physical_condition: str,
        behavioral_indicators: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        # Generate ticket number (e.g. RES-YYYYMMDD-XXXX)
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        rand_suffix = "".join(secrets.choice("0123456789") for _ in range(4))
        ticket_number = f"RES-{date_str}-{rand_suffix}"

        request = RescueRequest(
            ticket_number=ticket_number,
            reporter_name=reporter_name,
            reporter_phone=reporter_phone,
            reporter_email=reporter_email,
            is_anonymous=is_anonymous,
            location_address=location_address,
            location_landmark=location_landmark,
            latitude=latitude,
            longitude=longitude,
            animal_count=animal_count,
            physical_condition=physical_condition,
            behavioral_indicators=behavioral_indicators,
            status=RescueStatus.REPORTED,
        )
        await self._repo.create_request(request)
        res = await self._repo.get_request_by_id(request.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created rescue request.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.RESCUE_REPORTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_id": str(res.id),
                    "ticket_number": ticket_number,
                    "is_anonymous": is_anonymous,
                },
            )

        return res

    async def verify_request(
        self,
        request_id: uuid.UUID,
        *,
        approve: bool,
        rationale: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")

        if request.status != RescueStatus.REPORTED:
            raise ConflictError(f"Cannot verify request in status: {request.status}")

        if approve:
            request.status = RescueStatus.VERIFIED
        else:
            request.status = RescueStatus.REJECTED
            request.rejection_rationale = rationale

        await self._repo._session.flush()

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
                    "new_status": request.status.value,
                    "rationale": rationale,
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
            notes=notes,
        )
        await self._repo.create_dispatch(dispatch)

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

        elif status == RescueStatus.REJECTED:  # representing a failed rescue
            dispatch.failed_at = now
            dispatch.failure_reason = failure_reason or "Failed rescue"
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
                    "old_status": old_status.value,
                    "new_status": status.value,
                    "failure_reason": failure_reason,
                },
            )

        return res

    async def get_request(self, request_id: uuid.UUID) -> RescueRequest:
        request = await self._repo.get_request_by_id(request_id)
        if request is None:
            raise NotFoundError("Rescue request not found.")
        return request

    async def list_requests(self, status: RescueStatus | None = None) -> Sequence[RescueRequest]:
        return await self._repo.list_requests(status)

    async def list_requests_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: RescueStatus | None = None,
    ) -> PaginatedResponse[RescueRequestResponse]:
        results, total = await self._repo.list_paginated(
            page=page, sort=sort, search_term=search_term, status=status
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
        updated = await self._repo.bulk_update_status(ids, status)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.BULK_RESCUE_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "rescue_ids": [str(i) for i in ids],
                    "status": status.value,
                    "count": updated,
                },
            )

        return updated

    async def bulk_soft_delete(
        self,
        ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = 0
        for request_id in ids:
            request = await self._repo.get_request_by_id(request_id)
            if request is not None:
                request.deleted_at = datetime.now(UTC)
                count += 1

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
