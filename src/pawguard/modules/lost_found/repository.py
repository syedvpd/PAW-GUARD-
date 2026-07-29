"""Data access for the Lost & Found module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.lost_found.models import FoundReport, LostReport, ReportMatch, ReportStatus


class LostFoundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_lost_report(self, report: LostReport) -> LostReport:
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_lost_report_by_id(self, report_id: uuid.UUID) -> LostReport | None:
        stmt = (
            select(LostReport)
            .options(selectinload(LostReport.user))
            .where(LostReport.id == report_id, LostReport.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_lost_reports(self, status: ReportStatus | None = None) -> Sequence[LostReport]:
        stmt = (
            select(LostReport)
            .options(selectinload(LostReport.user))
            .where(LostReport.deleted_at.is_(None))
            .order_by(LostReport.lost_at.desc())
        )
        if status is not None:
            stmt = stmt.where(LostReport.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_found_report(self, report: FoundReport) -> FoundReport:
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_found_report_by_id(self, report_id: uuid.UUID) -> FoundReport | None:
        stmt = (
            select(FoundReport)
            .options(selectinload(FoundReport.user))
            .where(FoundReport.id == report_id, FoundReport.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_found_reports(self, status: ReportStatus | None = None) -> Sequence[FoundReport]:
        stmt = (
            select(FoundReport)
            .options(selectinload(FoundReport.user))
            .where(FoundReport.deleted_at.is_(None))
            .order_by(FoundReport.found_at.desc())
        )
        if status is not None:
            stmt = stmt.where(FoundReport.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_match(self, match: ReportMatch) -> ReportMatch:
        self._session.add(match)
        await self._session.flush()
        return match

    async def get_match_by_id(self, match_id: uuid.UUID) -> ReportMatch | None:
        stmt = (
            select(ReportMatch)
            .options(selectinload(ReportMatch.lost_report), selectinload(ReportMatch.found_report))
            .where(ReportMatch.id == match_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_matches_for_lost_report(self, lost_report_id: uuid.UUID) -> Sequence[ReportMatch]:
        stmt = (
            select(ReportMatch)
            .options(selectinload(ReportMatch.found_report))
            .where(ReportMatch.lost_report_id == lost_report_id)
            .order_by(ReportMatch.confidence_score.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_matches_for_found_report(self, found_report_id: uuid.UUID) -> Sequence[ReportMatch]:
        stmt = (
            select(ReportMatch)
            .options(selectinload(ReportMatch.lost_report))
            .where(ReportMatch.found_report_id == found_report_id)
            .order_by(ReportMatch.confidence_score.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()
