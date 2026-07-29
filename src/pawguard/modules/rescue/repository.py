"""Data access for the Emergency Rescue module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.rescue.models import RescueDispatch, RescueReport, RescueRequest, RescueStatus


class RescueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_request(self, request: RescueRequest) -> RescueRequest:
        self._session.add(request)
        await self._session.flush()
        return request

    async def get_request_by_id(self, request_id: uuid.UUID) -> RescueRequest | None:
        stmt = (
            select(RescueRequest)
            .options(
                selectinload(RescueRequest.dispatch),
                selectinload(RescueRequest.reports)
            )
            .where(RescueRequest.id == request_id, RescueRequest.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_request_by_ticket(self, ticket_number: str) -> RescueRequest | None:
        stmt = (
            select(RescueRequest)
            .options(
                selectinload(RescueRequest.dispatch),
                selectinload(RescueRequest.reports)
            )
            .where(RescueRequest.ticket_number == ticket_number, RescueRequest.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_requests(self, status: RescueStatus | None = None) -> Sequence[RescueRequest]:
        stmt = (
            select(RescueRequest)
            .options(
                selectinload(RescueRequest.dispatch),
                selectinload(RescueRequest.reports)
            )
            .where(RescueRequest.deleted_at.is_(None))
            .order_by(RescueRequest.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(RescueRequest.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_dispatch(self, dispatch: RescueDispatch) -> RescueDispatch:
        self._session.add(dispatch)
        await self._session.flush()
        return dispatch

    async def get_dispatch_by_request_id(self, request_id: uuid.UUID) -> RescueDispatch | None:
        stmt = select(RescueDispatch).where(RescueDispatch.rescue_request_id == request_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_report(self, report: RescueReport) -> RescueReport:
        self._session.add(report)
        await self._session.flush()
        return report
