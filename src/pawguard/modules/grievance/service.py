"""GrievanceService: owns complaint and feedback business behaviour (RULE-003)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.core.logging import get_logger
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginationMeta
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.grievance.models import (
    DEFAULT_SLA_HOURS,
    GrievanceComment,
    GrievanceStatus,
    GrievanceTicket,
    ServiceFeedback,
)
from pawguard.modules.grievance.repository import GrievanceRepository
from pawguard.modules.grievance.schemas import (
    CommentCreate,
    GrievanceCreate,
    GrievanceEscalate,
    GrievanceListFilter,
    GrievanceUpdate,
    ServiceFeedbackCreate,
)
from pawguard.services.audit_service import AuditService

logger = get_logger(__name__)

VALID_TRANSITIONS: dict[GrievanceStatus, set[GrievanceStatus]] = {
    GrievanceStatus.OPEN: {GrievanceStatus.INVESTIGATING, GrievanceStatus.CLOSED},
    GrievanceStatus.INVESTIGATING: {
        GrievanceStatus.AWAITING_RESPONSE,
        GrievanceStatus.RESOLVED,
        GrievanceStatus.CLOSED,
    },
    GrievanceStatus.AWAITING_RESPONSE: {
        GrievanceStatus.INVESTIGATING,
        GrievanceStatus.RESOLVED,
        GrievanceStatus.CLOSED,
    },
    GrievanceStatus.RESOLVED: {GrievanceStatus.CLOSED, GrievanceStatus.OPEN},
    GrievanceStatus.CLOSED: set(),
}


class GrievanceService:
    def __init__(
        self,
        repository: GrievanceRepository,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service

    async def _resolve_responsible_admin_id(self, facility_id: uuid.UUID | None) -> uuid.UUID | None:
        """The Rescue Centre Admin accountable for a facility (PRR §3.14).

        §3.14 requires a grievance to reach "the appropriate Rescue Centre
        Administrator (i.e. the one tied to the relevant shelter/zone, not
        all admins)". Returns None when the ticket names no facility or no
        admin manages it, leaving the ticket unassigned for manual triage
        rather than guessing.
        """
        if facility_id is None:
            return None
        return await self._repo.get_facility_admin_id(facility_id)

    async def submit_complaint(self, payload: GrievanceCreate) -> GrievanceTicket:
        sla_due_at = datetime.now(UTC) + timedelta(hours=DEFAULT_SLA_HOURS)
        data = payload.model_dump()
        # PRR §3.14 internal resolution workflow: route on arrival to the
        # admin responsible for the named shelter/zone instead of dropping
        # every public complaint into one shared unassigned queue.
        assigned_to = await self._resolve_responsible_admin_id(data.get("facility_id"))
        ticket = await self._repo.create_ticket(
            GrievanceTicket(**data, sla_due_at=sla_due_at, assigned_to_admin_id=assigned_to)
        )
        try:
            from pawguard.modules.notifications.governance_service import (
                dispatch_governed_notification,
            )

            await dispatch_governed_notification(
                self._repo._session,
                trigger_code="grievance_submitted",
                module_name="grievance",
                title=f"New Grievance Submitted: {ticket.subject[:30]}",
                body=f"A new grievance ticket #{ticket.ticket_number or ticket.id} has been submitted.",
                action_url=f"/grievances/{ticket.id}",
            )
        except Exception as exc:
            logger.warning("failed_sending_grievance_submission_push", error=str(exc))
        return ticket

    async def update_ticket(
        self,
        ticket_id: uuid.UUID,
        payload: GrievanceUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> GrievanceTicket:
        ticket = await self._repo.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError("Grievance ticket not found.")

        if (
            payload.status is not None
            and payload.status != ticket.status
            and payload.status not in VALID_TRANSITIONS.get(ticket.status, set())
        ):
            raise ValidationFailedError(
                f"Cannot transition from {ticket.status} to {payload.status}."
            )

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(ticket, field, value)

        await self._repo._session.flush()
        await self._repo._session.refresh(ticket)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.GRIEVANCE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "ticket_id": str(ticket_id),
                    "changes": payload.model_dump(exclude_unset=True),
                },
            )

        return ticket

    async def update_ticket_status(
        self,
        ticket_id: uuid.UUID,
        new_status: GrievanceStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> GrievanceTicket:
        ticket = await self._repo.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError("Grievance ticket not found.")

        if new_status != ticket.status and new_status not in VALID_TRANSITIONS.get(
            ticket.status, set()
        ):
            raise ValidationFailedError(f"Cannot transition from {ticket.status} to {new_status}.")

        ticket.status = new_status
        await self._repo._session.flush()
        await self._repo._session.refresh(ticket)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.GRIEVANCE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "ticket_id": str(ticket_id),
                    "changes": {"status": new_status},
                },
            )

        complainant_id = getattr(ticket, "complainant_user_id", None)
        if complainant_id:
            try:
                from pawguard.modules.notifications.governance_service import (
                    dispatch_governed_notification,
                )

                await dispatch_governed_notification(
                    self._repo._session,
                    trigger_code="grievance_status_updated",
                    module_name="grievance",
                    title=f"Grievance Ticket Status: {new_status.value.upper()}",
                    body=f"Your grievance ticket #{ticket.ticket_number or ticket.id} has been updated to {new_status.value}.",
                    target_user_ids=[complainant_id],
                    action_url=f"/grievances/my/{ticket.id}",
                )
            except Exception as exc:
                logger.warning("failed_sending_grievance_status_push", error=str(exc))

        return ticket

    async def assign_ticket(
        self,
        ticket_id: uuid.UUID,
        admin_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> GrievanceTicket:
        ticket = await self._repo.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError("Grievance ticket not found.")
        previous_admin_id = ticket.assigned_to_admin_id
        ticket.assigned_to_admin_id = admin_id
        await self._repo._session.flush()
        await self._repo._session.refresh(ticket)

        # Push notification to assigned admin
        try:
            from pawguard.modules.notifications.repository import NotificationRepository
            from pawguard.modules.notifications.service import NotificationService

            notification_svc = NotificationService(
                repository=NotificationRepository(self._repo._session)
            )
            await notification_svc._send_push_to_users(
                [admin_id],
                "Grievance Ticket Assigned",
                f"Grievance ticket {ticket.id} has been assigned to you.",
                f"/api/v1/grievance/{ticket.id}",
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to send assignment push for ticket %s: %s", ticket_id, exc
            )

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.GRIEVANCE_ASSIGNED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"ticket_id": str(ticket_id), "assigned_to": str(admin_id)},
                # PRR §6.1 requires Pre/Post State Data, not just metadata.
                before_state={"assigned_to_admin_id": previous_admin_id},
                after_state={"assigned_to_admin_id": admin_id},
            )

        return ticket

    async def escalate_ticket(
        self,
        ticket_id: uuid.UUID,
        payload: GrievanceEscalate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> GrievanceTicket:
        ticket = await self._repo.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError("Grievance ticket not found.")
        if ticket.status == GrievanceStatus.CLOSED:
            raise ValidationFailedError("Cannot escalate a closed ticket.")

        before_state = {
            "escalation_level": ticket.escalation_level,
            "escalated_at": ticket.escalated_at,
            "escalated_to_admin_id": ticket.escalated_to_admin_id,
        }
        ticket.escalation_level += 1
        ticket.escalated_at = datetime.now(UTC)
        ticket.escalated_to_admin_id = payload.escalated_to_admin_id
        await self._repo._session.flush()
        await self._repo._session.refresh(ticket)

        # Trigger notification alert to the escalated admin (PRD 3.14 gap)
        try:
            from pawguard.modules.notifications.repository import NotificationRepository
            from pawguard.modules.notifications.schemas import NotificationCreate
            from pawguard.modules.notifications.service import NotificationService

            notification_svc = NotificationService(
                repository=NotificationRepository(self._repo._session)
            )
            await notification_svc.create_notification(
                payload=NotificationCreate(
                    user_id=payload.escalated_to_admin_id,
                    title="Grievance Ticket Escalated",
                    body=(
                        f"Grievance ticket {ticket.id} has been escalated to "
                        f"you (Level {ticket.escalation_level}). Reason: "
                        f"{payload.reason or 'None'}."
                    ),
                    notification_type="grievance_escalation",
                    action_url=f"/api/v1/grievance/{ticket.id}",
                )
            )
            # Push notification for escalation
            await notification_svc._send_push_to_users(
                [payload.escalated_to_admin_id],
                "Grievance Ticket Escalated",
                f"Grievance ticket {ticket.id} has been escalated to you.",
                f"/api/v1/grievance/{ticket.id}",
            )
        except Exception as notif_exc:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to send notification for grievance escalation on ticket %s: %s",
                ticket.id,
                notif_exc,
                exc_info=True,
            )

        if self._audit and actor_id:
            await self._audit.record(
                # Its own action code, not the generic GRIEVANCE_UPDATED, so
                # PRR §3.14 escalations are queryable as escalations.
                event_type=AuthAuditEventType.GRIEVANCE_ESCALATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "ticket_id": str(ticket_id),
                    "escalation_level": ticket.escalation_level,
                    "escalated_to_admin_id": str(payload.escalated_to_admin_id),
                    "reason": payload.reason,
                },
                before_state=before_state,
                after_state={
                    "escalation_level": ticket.escalation_level,
                    "escalated_at": ticket.escalated_at,
                    "escalated_to_admin_id": ticket.escalated_to_admin_id,
                },
            )

        return ticket

    async def get_ticket(self, ticket_id: uuid.UUID) -> GrievanceTicket:
        ticket = await self._repo.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError("Grievance ticket not found.")
        return ticket

    async def list_tickets(
        self,
        *,
        page_params: PageParams | None = None,
        filter_params: GrievanceListFilter | None = None,
        facility_ids: Sequence[uuid.UUID] | None = None,
    ) -> tuple[list[GrievanceTicket], PaginationMeta]:
        status = filter_params.status if filter_params else None
        complaint_type = filter_params.complaint_type if filter_params else None
        assigned_to = filter_params.assigned_to_admin_id if filter_params else None
        search = filter_params.search if filter_params else None

        total = await self._repo.count_tickets(
            status=status,
            complaint_type=complaint_type,
            assigned_to_admin_id=assigned_to,
            search=search,
            facility_ids=facility_ids,
        )
        tickets = await self._repo.list_tickets(
            page_params=page_params,
            status=status,
            complaint_type=complaint_type,
            assigned_to_admin_id=assigned_to,
            search=search,
            facility_ids=facility_ids,
        )
        meta = build_pagination_meta(total=total, params=page_params or PageParams())
        return list(tickets), meta

    async def add_comment(
        self,
        ticket_id: uuid.UUID,
        payload: CommentCreate,
        *,
        author_id: uuid.UUID | None = None,
    ) -> GrievanceComment:
        ticket = await self._repo.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError("Grievance ticket not found.")

        comment = GrievanceComment(
            ticket_id=ticket_id,
            author_id=author_id,
            body=payload.body,
            is_internal=payload.is_internal,
        )
        created = await self._repo.create_comment(comment)

        if ticket.first_responded_at is None:
            ticket.first_responded_at = datetime.now(UTC)
            await self._repo._session.flush()

        return created

    async def list_comments(self, ticket_id: uuid.UUID) -> list[GrievanceComment]:
        ticket = await self._repo.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError("Grievance ticket not found.")
        return list(await self._repo.list_comments(ticket_id))

    async def submit_feedback(self, payload: ServiceFeedbackCreate) -> ServiceFeedback:
        return await self._repo.create_feedback(ServiceFeedback(**payload.model_dump()))

    async def list_feedback(
        self, *, page_params: PageParams | None = None
    ) -> tuple[list[ServiceFeedback], PaginationMeta]:
        total = await self._repo.count_feedback()
        feedback = await self._repo.list_feedback(page_params=page_params)
        meta = build_pagination_meta(total=total, params=page_params or PageParams())
        return list(feedback), meta

    # ── Soft delete ─────────────────────────────────────────────────────────

    async def soft_delete_ticket(self, ticket_id: uuid.UUID) -> None:
        ticket = await self._repo.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError("Grievance ticket not found.")
        await self._repo.soft_delete_ticket(ticket_id)

    async def soft_delete_feedback(self, feedback_id: uuid.UUID) -> None:
        fb = await self._repo.get_feedback(feedback_id)
        if fb is None:
            raise NotFoundError("Feedback not found.")
        await self._repo.soft_delete_feedback(feedback_id)

    # ── Bulk operations ─────────────────────────────────────────────────────

    async def bulk_delete_tickets(self, ids: list[uuid.UUID]) -> int:
        return await self._repo.bulk_soft_delete_tickets(ids)

    async def bulk_update_ticket_status(self, ids: list[uuid.UUID], status: GrievanceStatus) -> int:
        return await self._repo.bulk_update_ticket_status(ids, status)

    async def bulk_delete_feedback(self, ids: list[uuid.UUID]) -> int:
        return await self._repo.bulk_soft_delete_feedback(ids)
