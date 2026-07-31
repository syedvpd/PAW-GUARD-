"""Data access for grievance module."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
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

    async def get_ticket(self, ticket_id: uuid.UUID) -> GrievanceTicket | None:
        stmt = select(GrievanceTicket).where(
            GrievanceTicket.id == ticket_id,
            GrievanceTicket.is_deleted.is_(False),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_tickets(
        self,
        *,
        status: GrievanceStatus | None = None,
        complaint_type: str | None = None,
        assigned_to_admin_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count(GrievanceTicket.id)).where(GrievanceTicket.is_deleted.is_(False))
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
    ) -> Sequence[GrievanceTicket]:
        stmt = select(GrievanceTicket).where(GrievanceTicket.is_deleted.is_(False))
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
        stmt = select(func.count(ServiceFeedback.id)).where(ServiceFeedback.is_deleted.is_(False))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_feedback(
        self, *, page_params: PageParams | None = None
    ) -> Sequence[ServiceFeedback]:
        stmt = select(ServiceFeedback).where(ServiceFeedback.is_deleted.is_(False))
        stmt = stmt.order_by(ServiceFeedback.created_at.desc())
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_feedback(self, feedback_id: uuid.UUID) -> ServiceFeedback | None:
        stmt = select(ServiceFeedback).where(
            ServiceFeedback.id == feedback_id,
            ServiceFeedback.is_deleted.is_(False),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # ── Soft delete ─────────────────────────────────────────────────────────

    async def soft_delete_ticket(self, ticket_id: uuid.UUID) -> None:
        stmt = select(GrievanceTicket).where(
            GrievanceTicket.id == ticket_id,
            GrievanceTicket.is_deleted.is_(False),
        )
        ticket = (await self._session.execute(stmt)).scalar_one_or_none()
        if ticket:
            ticket.is_deleted = True

    async def soft_delete_feedback(self, feedback_id: uuid.UUID) -> None:
        stmt = select(ServiceFeedback).where(
            ServiceFeedback.id == feedback_id,
            ServiceFeedback.is_deleted.is_(False),
        )
        fb = (await self._session.execute(stmt)).scalar_one_or_none()
        if fb:
            fb.is_deleted = True

    # ── Bulk operations ─────────────────────────────────────────────────────

    async def bulk_soft_delete_tickets(self, ids: list[uuid.UUID]) -> int:
        stmt = (
            select(GrievanceTicket)
            .where(GrievanceTicket.id.in_(ids), GrievanceTicket.is_deleted.is_(False))
        )
        tickets = (await self._session.execute(stmt)).scalars().all()
        for t in tickets:
            t.is_deleted = True
        return len(tickets)

    async def bulk_update_ticket_status(self, ids: list[uuid.UUID], status: GrievanceStatus) -> int:
        stmt = (
            select(GrievanceTicket)
            .where(GrievanceTicket.id.in_(ids), GrievanceTicket.is_deleted.is_(False))
        )
        tickets = (await self._session.execute(stmt)).scalars().all()
        for t in tickets:
            t.status = status
        return len(tickets)

    async def bulk_soft_delete_feedback(self, ids: list[uuid.UUID]) -> int:
        stmt = (
            select(ServiceFeedback)
            .where(ServiceFeedback.id.in_(ids), ServiceFeedback.is_deleted.is_(False))
        )
        feedbacks = (await self._session.execute(stmt)).scalars().all()
        for fb in feedbacks:
            fb.is_deleted = True
        return len(feedbacks)
