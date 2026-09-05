"""Data access for the Lost & Found module. Repositories never contain business decisions."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.auth.models import User
from pawguard.modules.lost_found.models import (
    FoundReport,
    LostReport,
    PetSighting,
    ReportMatch,
    ReportStatus,
    Species,
)


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
            .options(
                selectinload(LostReport.user).selectinload(User.roles),
                selectinload(LostReport.media),
            )
            .where(LostReport.id == report_id, LostReport.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_lost_report_for_broadcast(self, report_id: uuid.UUID) -> LostReport | None:
        stmt = (
            select(LostReport)
            .where(LostReport.id == report_id, LostReport.deleted_at.is_(None))
            .with_for_update()
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_lost_reports(self, status: ReportStatus | None = None) -> Sequence[LostReport]:
        stmt = (
            select(LostReport)
            .options(
                selectinload(LostReport.user).selectinload(User.roles),
                selectinload(LostReport.media),
            )
            .where(LostReport.deleted_at.is_(None))
            .order_by(LostReport.lost_at.desc())
        )
        if status is not None:
            stmt = stmt.where(LostReport.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    async def find_active_lost_duplicate(
        self,
        *,
        user_id: uuid.UUID,
        companion_pet_id: uuid.UUID | None = None,
        microchip_id: str | None = None,
        species: Species | None = None,
        pet_name: str | None = None,
        breed: str | None = None,
        location_address: str | None = None,
    ) -> LostReport | None:
        """Find an existing ACTIVE lost report for duplicate prevention.

        Safe matching criteria:
        1. If companion_pet_id is provided: matches user_id + companion_pet_id.
        2. Else if microchip_id is provided and non-empty: matches user_id + microchip_id.
        3. Otherwise: matches user_id + species + pet_name + breed + location_address.
        Only reports with status == ReportStatus.ACTIVE are matched.
        """
        stmt = (
            select(LostReport)
            .options(
                selectinload(LostReport.user).selectinload(User.roles),
                selectinload(LostReport.media),
            )
            .where(
                LostReport.user_id == user_id,
                LostReport.status == ReportStatus.ACTIVE,
                LostReport.deleted_at.is_(None),
            )
        )

        if companion_pet_id is not None:
            stmt = stmt.where(LostReport.companion_pet_id == companion_pet_id)
        elif microchip_id and microchip_id.strip():
            stmt = stmt.where(
                func.lower(func.trim(LostReport.microchip_id)) == microchip_id.strip().lower()
            )
        else:
            if species is not None:
                stmt = stmt.where(LostReport.species == species)
            if pet_name:
                stmt = stmt.where(
                    func.lower(func.trim(LostReport.pet_name)) == pet_name.strip().lower()
                )
            if breed:
                stmt = stmt.where(func.lower(func.trim(LostReport.breed)) == breed.strip().lower())
            if location_address:
                stmt = stmt.where(
                    func.lower(func.trim(LostReport.location_address))
                    == location_address.strip().lower()
                )

        stmt = stmt.order_by(LostReport.created_at.desc()).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_active_found_duplicate(
        self,
        *,
        user_id: uuid.UUID,
        species: Species,
        breed_observed: str,
        location_address: str,
    ) -> FoundReport | None:
        """Find an existing ACTIVE found report for duplicate prevention.

        Matches user_id + species + breed_observed + location_address for ACTIVE reports.
        """
        stmt = (
            select(FoundReport)
            .options(
                selectinload(FoundReport.user).selectinload(User.roles),
                selectinload(FoundReport.media),
            )
            .where(
                FoundReport.user_id == user_id,
                FoundReport.status == ReportStatus.ACTIVE,
                FoundReport.deleted_at.is_(None),
                FoundReport.species == species,
                func.lower(func.trim(FoundReport.breed_observed)) == breed_observed.strip().lower(),
                func.lower(func.trim(FoundReport.location_address))
                == location_address.strip().lower(),
            )
            .order_by(FoundReport.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_found_report(self, report: FoundReport) -> FoundReport:
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_found_report_by_id(self, report_id: uuid.UUID) -> FoundReport | None:
        stmt = (
            select(FoundReport)
            .options(
                selectinload(FoundReport.user).selectinload(User.roles),
                selectinload(FoundReport.media),
            )
            .where(FoundReport.id == report_id, FoundReport.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_found_reports(self, status: ReportStatus | None = None) -> Sequence[FoundReport]:
        stmt = (
            select(FoundReport)
            .options(
                selectinload(FoundReport.user).selectinload(User.roles),
                selectinload(FoundReport.media),
            )
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
            .options(
                selectinload(ReportMatch.lost_report)
                .selectinload(LostReport.user)
                .selectinload(User.roles),
                selectinload(ReportMatch.lost_report).selectinload(LostReport.media),
                selectinload(ReportMatch.found_report)
                .selectinload(FoundReport.user)
                .selectinload(User.roles),
                selectinload(ReportMatch.found_report).selectinload(FoundReport.media),
            )
            .where(ReportMatch.id == match_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_matches_for_lost_report(
        self,
        lost_report_id: uuid.UUID,
    ) -> Sequence[ReportMatch]:
        stmt = (
            select(ReportMatch)
            .options(
                selectinload(ReportMatch.lost_report)
                .selectinload(LostReport.user)
                .selectinload(User.roles),
                selectinload(ReportMatch.lost_report).selectinload(LostReport.media),
                selectinload(ReportMatch.found_report)
                .selectinload(FoundReport.user)
                .selectinload(User.roles),
                selectinload(ReportMatch.found_report).selectinload(FoundReport.media),
            )
            .where(ReportMatch.lost_report_id == lost_report_id)
            .order_by(ReportMatch.confidence_score.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_matches_for_found_report(
        self,
        found_report_id: uuid.UUID,
    ) -> Sequence[ReportMatch]:
        stmt = (
            select(ReportMatch)
            .options(
                selectinload(ReportMatch.lost_report)
                .selectinload(LostReport.user)
                .selectinload(User.roles),
                selectinload(ReportMatch.lost_report).selectinload(LostReport.media),
                selectinload(ReportMatch.found_report)
                .selectinload(FoundReport.user)
                .selectinload(User.roles),
                selectinload(ReportMatch.found_report).selectinload(FoundReport.media),
            )
            .where(ReportMatch.found_report_id == found_report_id)
            .order_by(ReportMatch.confidence_score.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_lost_reports_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: ReportStatus | None = None,
        species: Species | None = None,
    ) -> tuple[Sequence[LostReport], int]:
        stmt = (
            select(LostReport)
            .options(
                selectinload(LostReport.user).selectinload(User.roles),
                selectinload(LostReport.media),
            )
            .where(LostReport.deleted_at.is_(None))
        )

        search_filter = build_search_filter(
            LostReport,
            search_term,
            ("pet_name", "breed", "color", "location_address"),
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(LostReport.status == status)
        if species is not None:
            stmt = stmt.where(LostReport.species == species)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        valid_fields = {"created_at", "lost_at", "pet_name", "breed", "status"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_found_reports_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: ReportStatus | None = None,
        species: Species | None = None,
    ) -> tuple[Sequence[FoundReport], int]:
        stmt = (
            select(FoundReport)
            .options(
                selectinload(FoundReport.user).selectinload(User.roles),
                selectinload(FoundReport.media),
            )
            .where(FoundReport.deleted_at.is_(None))
        )

        search_filter = build_search_filter(
            FoundReport,
            search_term,
            ("breed_observed", "color_observed", "location_address"),
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(FoundReport.status == status)
        if species is not None:
            stmt = stmt.where(FoundReport.species == species)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        valid_fields = {"created_at", "found_at", "status"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_matches_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        lost_report_id: uuid.UUID | None = None,
        found_report_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[ReportMatch], int]:
        stmt = select(ReportMatch).options(
            selectinload(ReportMatch.lost_report)
            .selectinload(LostReport.user)
            .selectinload(User.roles),
            selectinload(ReportMatch.lost_report).selectinload(LostReport.media),
            selectinload(ReportMatch.found_report)
            .selectinload(FoundReport.user)
            .selectinload(User.roles),
            selectinload(ReportMatch.found_report).selectinload(FoundReport.media),
        )

        if lost_report_id is not None:
            stmt = stmt.where(ReportMatch.lost_report_id == lost_report_id)
        if found_report_id is not None:
            stmt = stmt.where(ReportMatch.found_report_id == found_report_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        valid_fields = {"created_at", "confidence_score", "status"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def soft_delete_lost_report(self, report_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime

        stmt = select(LostReport).where(LostReport.id == report_id, LostReport.deleted_at.is_(None))
        report = (await self._session.execute(stmt)).scalar_one_or_none()
        if report is None:
            return False
        report.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def soft_delete_found_report(self, report_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime

        stmt = select(FoundReport).where(
            FoundReport.id == report_id, FoundReport.deleted_at.is_(None)
        )
        report = (await self._session.execute(stmt)).scalar_one_or_none()
        if report is None:
            return False
        report.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def bulk_delete_lost_reports(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        stmt = select(LostReport).where(LostReport.id.in_(ids), LostReport.deleted_at.is_(None))
        reports = (await self._session.execute(stmt)).scalars().all()
        for r in reports:
            r.deleted_at = now
        await self._session.flush()
        return len(reports)

    async def bulk_delete_found_reports(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        stmt = select(FoundReport).where(FoundReport.id.in_(ids), FoundReport.deleted_at.is_(None))
        reports = (await self._session.execute(stmt)).scalars().all()
        for r in reports:
            r.deleted_at = now
        await self._session.flush()
        return len(reports)

    async def create_sighting(self, sighting: PetSighting) -> PetSighting:
        self._session.add(sighting)
        await self._session.flush()
        return sighting

    async def get_active_lost_report_by_pet_id(self, pet_id: uuid.UUID) -> LostReport | None:
        stmt = (
            select(LostReport)
            .where(
                LostReport.companion_pet_id == pet_id,
                LostReport.status == ReportStatus.ACTIVE,
                LostReport.deleted_at.is_(None),
            )
            .order_by(LostReport.lost_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def get_active_lost_report_by_user_and_pet_name(
        self, user_id: uuid.UUID, pet_name: str
    ) -> LostReport | None:
        stmt = (
            select(LostReport)
            .where(
                LostReport.user_id == user_id,
                func.lower(LostReport.pet_name) == func.lower(pet_name),
                LostReport.status == ReportStatus.ACTIVE,
                LostReport.deleted_at.is_(None),
            )
            .order_by(LostReport.lost_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().first()
