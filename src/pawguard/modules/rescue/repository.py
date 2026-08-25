"""Data access for the Emergency Rescue module."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.rescue.models import (
    RescueDispatch,
    RescueDispatchAgent,
    RescueEscalationStatus,
    RescueReport,
    RescueRequest,
    RescueSeverity,
    RescueStatus,
)


class RescueRepository:
    SEARCH_FIELDS = ("ticket_number", "reporter_name", "reporter_phone", "location_address")
    SORTABLE_FIELDS = {
        "ticket_number",
        "reporter_name",
        "status",
        "severity",
        "is_urgent",
        "created_at",
        "updated_at",
        "animal_count",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_stmt(self) -> Any:
        return (
            select(RescueRequest)
            .options(
                selectinload(RescueRequest.dispatch)
                .selectinload(RescueDispatch.agents)
                .selectinload(RescueDispatchAgent.agent),
                selectinload(RescueRequest.dispatch).selectinload(RescueDispatch.driver),
                selectinload(RescueRequest.reports),
                selectinload(RescueRequest.dog_profile),
            )
            .where(RescueRequest.deleted_at.is_(None))
        )

    async def user_exists(self, user_id: uuid.UUID) -> bool:
        from pawguard.modules.auth.models import User

        stmt = select(exists().where(User.id == user_id, User.deleted_at.is_(None)))
        return bool((await self._session.execute(stmt)).scalar())

    async def create_request(self, request: RescueRequest) -> RescueRequest:
        self._session.add(request)
        await self._session.flush()
        return request

    async def get_request_by_id(self, request_id: uuid.UUID) -> RescueRequest | None:
        stmt = self._base_stmt().where(RescueRequest.id == request_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_request_by_ticket(self, ticket_number: str) -> RescueRequest | None:
        stmt = self._base_stmt().where(RescueRequest.ticket_number == ticket_number)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_request_by_ticket_and_phone(
        self, ticket_number: str, phone: str
    ) -> RescueRequest | None:
        """Public case-status lookup (PRR 3.2): the reporter verifies ownership
        with the ticket number AND the phone they reported with, so guessing a
        ticket number alone cannot leak another person's case."""
        stmt = self._base_stmt().where(
            RescueRequest.ticket_number == ticket_number,
            RescueRequest.reporter_phone == phone,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_requests(self, status: RescueStatus | None = None) -> Sequence[RescueRequest]:
        stmt = self._base_stmt().order_by(RescueRequest.created_at.desc())
        if status is not None:
            stmt = stmt.where(RescueRequest.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    async def list_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: RescueStatus | None = None,
        severity: RescueSeverity | None = None,
        urgent_only: bool | None = None,
        assigned_to_me: uuid.UUID | None = None,
    ) -> tuple[Sequence[RescueRequest], int]:
        stmt = self._base_stmt()

        search_filter = build_search_filter(RescueRequest, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(RescueRequest.status == status)

        if severity is not None:
            stmt = stmt.where(RescueRequest.severity == severity)

        if urgent_only is not None:
            stmt = stmt.where(RescueRequest.is_urgent.is_(urgent_only))

        if assigned_to_me is not None:
            # "My assigned cases" filter (PRR 3.2 field-agent interface): the
            # user is on the dispatch team when they are either the legacy
            # assigned_driver_id or a row in the dispatch-agent association
            # table. EXISTS keeps the row set distinct (no fan-out) so the
            # count query below stays correct.
            agent_scope = exists().where(
                RescueDispatchAgent.dispatch_id == RescueDispatch.id,
                RescueDispatchAgent.agent_id == assigned_to_me,
            )
            stmt = stmt.join(
                RescueDispatch, RescueDispatch.rescue_request_id == RescueRequest.id
            ).where(
                or_(
                    RescueDispatch.assigned_driver_id == assigned_to_me,
                    agent_scope,
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS)
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_by_ids(self, ids: list[uuid.UUID]) -> Sequence[RescueRequest]:
        stmt = self._base_stmt().where(RescueRequest.id.in_(ids))
        return (await self._session.execute(stmt)).scalars().all()

    async def bulk_soft_delete(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        from sqlalchemy import update

        stmt = (
            update(RescueRequest)
            .where(RescueRequest.id.in_(ids), RescueRequest.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def count_by_status(self) -> dict[str, int]:
        stmt = (
            select(RescueRequest.status, func.count())
            .where(RescueRequest.deleted_at.is_(None))
            .group_by(RescueRequest.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}

    async def create_dispatch(self, dispatch: RescueDispatch) -> RescueDispatch:
        self._session.add(dispatch)
        await self._session.flush()
        return dispatch

    async def create_dispatch_agent(self, agent: RescueDispatchAgent) -> RescueDispatchAgent:
        self._session.add(agent)
        await self._session.flush()
        return agent

    async def get_dispatch_by_request_id(self, request_id: uuid.UUID) -> RescueDispatch | None:
        stmt = (
            select(RescueDispatch)
            .options(
                selectinload(RescueDispatch.agents).selectinload(RescueDispatchAgent.agent),
                selectinload(RescueDispatch.driver),
                selectinload(RescueDispatch.rescue_request),
            )
            .where(RescueDispatch.rescue_request_id == request_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_dispatch_by_id(self, dispatch_id: uuid.UUID) -> RescueDispatch | None:
        stmt = (
            select(RescueDispatch)
            .options(
                selectinload(RescueDispatch.agents).selectinload(RescueDispatchAgent.agent),
                selectinload(RescueDispatch.driver),
                selectinload(RescueDispatch.rescue_request),
            )
            .where(RescueDispatch.id == dispatch_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_dispatches_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        escalated_only: bool | None = None,
    ) -> tuple[Sequence[RescueDispatch], int]:
        stmt = select(RescueDispatch).options(
            selectinload(RescueDispatch.agents).selectinload(RescueDispatchAgent.agent),
            selectinload(RescueDispatch.driver),
            selectinload(RescueDispatch.rescue_request),
        )

        if escalated_only is True:
            # Active escalations: type is set AND not yet resolved.
            stmt = stmt.where(
                RescueDispatch.escalation_type.is_not(None),
                RescueDispatch.escalation_status != RescueEscalationStatus.RESOLVED,
            )

        valid_fields = {
            "dispatched_at",
            "located_at",
            "rescued_at",
            "admitted_at",
            "failed_at",
            "escalation_type",
            "escalation_status",
            "created_at",
            "updated_at",
        }
        stmt = apply_sorting(stmt, sort, valid_fields)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def get_dispatch_counts(self) -> dict[str, int]:
        """Return centre-wide aggregate counts for the Rescue Admin dashboard.

        Single SQL query using conditional aggregation avoids N+1 queries.
        Escalated count excludes RESOLVED escalations so the dashboard badge
        reflects only *active* escalations.
        """
        from sqlalchemy import case, literal_column

        total_col = func.count(RescueDispatch.id).label("total_dispatches")
        active_col = func.sum(
            case(
                (
                    RescueRequest.status.not_in([RescueStatus.ADMITTED, RescueStatus.REJECTED]),
                    literal_column("1"),
                ),
                else_=literal_column("0"),
            )
        ).label("active_dispatches")
        escalated_col = func.sum(
            case(
                (
                    (RescueDispatch.escalation_type.is_not(None))
                    & (RescueDispatch.escalation_status != RescueEscalationStatus.RESOLVED),
                    literal_column("1"),
                ),
                else_=literal_column("0"),
            )
        ).label("escalated_dispatches")
        failed_col = func.sum(
            case(
                (RescueDispatch.failed_at.is_not(None), literal_column("1")),
                else_=literal_column("0"),
            )
        ).label("failed_dispatches")

        stmt = select(total_col, active_col, escalated_col, failed_col).join(
            RescueRequest, RescueDispatch.rescue_request_id == RescueRequest.id
        )
        row = (await self._session.execute(stmt)).one()
        return {
            "total_dispatches": int(row.total_dispatches or 0),
            "active_dispatches": int(row.active_dispatches or 0),
            "escalated_dispatches": int(row.escalated_dispatches or 0),
            "failed_dispatches": int(row.failed_dispatches or 0),
        }

    async def delete_dispatch(self, dispatch: RescueDispatch) -> None:
        await self._session.delete(dispatch)
        await self._session.flush()

    async def create_report(self, report: RescueReport) -> RescueReport:
        self._session.add(report)
        await self._session.flush()
        return report
