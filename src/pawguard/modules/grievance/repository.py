"""Data access for grievance module."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.modules.auth.models import Role, User, UserManagedFacility, UserRole
from pawguard.modules.grievance.models import (
    GrievanceComment,
    GrievanceStatus,
    GrievanceTicket,
    ServiceFeedback,
)


class GrievanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_ticket(self, ticket: GrievanceTicket) -> GrievanceTicket:
        self._session.add(ticket)
        await self._session.flush()
        return ticket

    async def get_facility_admin_id(self, facility_id: uuid.UUID) -> uuid.UUID | None:
        """The active rescue_centre_admin managing this facility (PRR §3.14).

        Returns None when nobody manages it, so the caller leaves the ticket
        unassigned rather than routing it to an arbitrary admin. If several
        admins manage the same facility the oldest account wins, purely so
        routing is deterministic.
        """
        # Matches either assignment mechanism (PRR §2.1): the legacy singular
        # column, or the many-to-many join table that supports an admin
        # covering several facilities.
        manages_facility = or_(
            User.managed_facility_id == facility_id,
            User.id.in_(
                select(UserManagedFacility.user_id).where(
                    UserManagedFacility.facility_id == facility_id
                )
            ),
        )
        stmt = (
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                manages_facility,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                Role.name == "rescue_centre_admin",
            )
            .order_by(User.created_at.asc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_ticket(self, ticket_id: uuid.UUID) -> GrievanceTicket | None:
        stmt = select(GrievanceTicket).where(
            GrievanceTicket.id == ticket_id,
            GrievanceTicket.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_tickets(
        self,
        *,
        status: GrievanceStatus | None = None,
        complaint_type: str | None = None,
        assigned_to_admin_id: uuid.UUID | None = None,
        search: str | None = None,
        facility_ids: Sequence[uuid.UUID] | None = None,
    ) -> int:
        stmt = select(func.count(GrievanceTicket.id)).where(GrievanceTicket.deleted_at.is_(None))
        if facility_ids is not None:
            # Must mirror list_tickets' scoping or the pagination total
            # would count tickets the caller isn't allowed to see.
            stmt = stmt.where(
                or_(
                    GrievanceTicket.facility_id.in_(facility_ids),
                    GrievanceTicket.facility_id.is_(None),
                )
            )
        if status:
            stmt = stmt.where(GrievanceTicket.status == status)
        if complaint_type:
            stmt = stmt.where(GrievanceTicket.complaint_type == complaint_type)
        if assigned_to_admin_id:
            stmt = stmt.where(GrievanceTicket.assigned_to_admin_id == assigned_to_admin_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    GrievanceTicket.reporter_name.ilike(like),
                    GrievanceTicket.reporter_phone.ilike(like),
                    GrievanceTicket.details.ilike(like),
                    GrievanceTicket.complaint_type.ilike(like),
                )
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_tickets(
        self,
        *,
        page_params: PageParams | None = None,
        status: GrievanceStatus | None = None,
        complaint_type: str | None = None,
        assigned_to_admin_id: uuid.UUID | None = None,
        search: str | None = None,
        facility_ids: Sequence[uuid.UUID] | None = None,
    ) -> Sequence[GrievanceTicket]:
        stmt = select(GrievanceTicket).where(GrievanceTicket.deleted_at.is_(None))
        if facility_ids is not None:
            # PRR §2.1 location scoping, derived server-side from the caller
            # (auth/scoping.py) - never from a client-supplied parameter.
            # Tickets with no facility stay visible so a complaint that
            # arrived without one can still be triaged and routed.
            stmt = stmt.where(
                or_(
                    GrievanceTicket.facility_id.in_(facility_ids),
                    GrievanceTicket.facility_id.is_(None),
                )
            )
        if status:
            stmt = stmt.where(GrievanceTicket.status == status)
        if complaint_type:
            stmt = stmt.where(GrievanceTicket.complaint_type == complaint_type)
        if assigned_to_admin_id:
            stmt = stmt.where(GrievanceTicket.assigned_to_admin_id == assigned_to_admin_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    GrievanceTicket.reporter_name.ilike(like),
                    GrievanceTicket.reporter_phone.ilike(like),
                    GrievanceTicket.details.ilike(like),
                    GrievanceTicket.complaint_type.ilike(like),
                )
            )
        stmt = stmt.order_by(GrievanceTicket.created_at.desc())
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_comment(self, comment: GrievanceComment) -> GrievanceComment:
        self._session.add(comment)
        await self._session.flush()
        return comment

    async def list_comments(self, ticket_id: uuid.UUID) -> Sequence[GrievanceComment]:
        stmt = (
            select(GrievanceComment)
            .where(GrievanceComment.ticket_id == ticket_id)
            .order_by(GrievanceComment.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_feedback(self, feedback: ServiceFeedback) -> ServiceFeedback:
        self._session.add(feedback)
        await self._session.flush()
        return feedback

    async def count_feedback(self) -> int:
        stmt = select(func.count(ServiceFeedback.id)).where(ServiceFeedback.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_feedback(
        self, *, page_params: PageParams | None = None
    ) -> Sequence[ServiceFeedback]:
        stmt = select(ServiceFeedback).where(ServiceFeedback.deleted_at.is_(None))
        stmt = stmt.order_by(ServiceFeedback.created_at.desc())
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_feedback(self, feedback_id: uuid.UUID) -> ServiceFeedback | None:
        stmt = select(ServiceFeedback).where(
            ServiceFeedback.id == feedback_id,
            ServiceFeedback.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # ── Soft delete ─────────────────────────────────────────────────────────

    async def soft_delete_ticket(self, ticket_id: uuid.UUID) -> None:
        stmt = select(GrievanceTicket).where(
            GrievanceTicket.id == ticket_id,
            GrievanceTicket.deleted_at.is_(None),
        )
        ticket = (await self._session.execute(stmt)).scalar_one_or_none()
        if ticket:
            ticket.deleted_at = datetime.now(UTC)

    async def soft_delete_feedback(self, feedback_id: uuid.UUID) -> None:
        stmt = select(ServiceFeedback).where(
            ServiceFeedback.id == feedback_id,
            ServiceFeedback.deleted_at.is_(None),
        )
        fb = (await self._session.execute(stmt)).scalar_one_or_none()
        if fb:
            fb.deleted_at = datetime.now(UTC)

    # ── Bulk operations ─────────────────────────────────────────────────────

    async def bulk_soft_delete_tickets(self, ids: list[uuid.UUID]) -> int:
        stmt = select(GrievanceTicket).where(
            GrievanceTicket.id.in_(ids), GrievanceTicket.deleted_at.is_(None)
        )
        tickets = (await self._session.execute(stmt)).scalars().all()
        for t in tickets:
            t.deleted_at = datetime.now(UTC)
        return len(tickets)

    async def bulk_update_ticket_status(self, ids: list[uuid.UUID], status: GrievanceStatus) -> int:
        stmt = select(GrievanceTicket).where(
            GrievanceTicket.id.in_(ids), GrievanceTicket.deleted_at.is_(None)
        )
        tickets = (await self._session.execute(stmt)).scalars().all()
        for t in tickets:
            t.status = status
        return len(tickets)

    async def bulk_soft_delete_feedback(self, ids: list[uuid.UUID]) -> int:
        stmt = select(ServiceFeedback).where(
            ServiceFeedback.id.in_(ids), ServiceFeedback.deleted_at.is_(None)
        )
        feedbacks = (await self._session.execute(stmt)).scalars().all()
        for fb in feedbacks:
            fb.deleted_at = datetime.now(UTC)
        return len(feedbacks)
