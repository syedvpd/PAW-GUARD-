"""Data access for the Shelter & Capacity Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.shelter.models import (
    DailyCareLog,
    FacilityStatus,
    FacilityTransfer,
    FacilityType,
    Kennel,
    KennelCleaningLog,
    SectionType,
    ShelterFacility,
    ShelterSection,
)


class ShelterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_facility(self, facility: ShelterFacility) -> ShelterFacility:
        self._session.add(facility)
        await self._session.flush()
        return facility

    async def get_facility(self, facility_id: uuid.UUID) -> ShelterFacility | None:
        stmt = (
            select(ShelterFacility)
            .where(ShelterFacility.id == facility_id, ShelterFacility.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_facility_by_name(self, name: str) -> ShelterFacility | None:
        stmt = select(ShelterFacility).where(
            ShelterFacility.name == name, ShelterFacility.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_facilities(self) -> Sequence[ShelterFacility]:
        stmt = (
            select(ShelterFacility)
            .where(ShelterFacility.deleted_at.is_(None))
            .order_by(ShelterFacility.name.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_section(self, section: ShelterSection) -> ShelterSection:
        self._session.add(section)
        await self._session.flush()
        return section

    async def get_section(self, section_id: uuid.UUID) -> ShelterSection | None:
        stmt = select(ShelterSection).where(ShelterSection.id == section_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_sections_by_facility(self, facility_id: uuid.UUID) -> Sequence[ShelterSection]:
        stmt = (
            select(ShelterSection)
            .where(ShelterSection.facility_id == facility_id)
            .order_by(ShelterSection.name.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_kennel(self, kennel: Kennel) -> Kennel:
        self._session.add(kennel)
        await self._session.flush()
        return kennel

    async def get_kennel(self, kennel_id: uuid.UUID) -> Kennel | None:
        stmt = select(Kennel).where(Kennel.id == kennel_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_kennel_for_update(self, kennel_id: uuid.UUID) -> Kennel | None:
        """Locks the kennel row (SELECT ... FOR UPDATE) for the rest of the
        transaction - serializes concurrent assignments so the capacity and
        sanitation check-then-act can't double-book a kennel."""
        from pawguard.core.config import get_settings
        from pawguard.core.constants import Environment

        stmt = select(Kennel).where(Kennel.id == kennel_id)
        if get_settings().environment != Environment.TEST:
            stmt = stmt.with_for_update()

        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_kennels_by_section(self, section_id: uuid.UUID) -> Sequence[Kennel]:
        stmt = (
            select(Kennel)
            .where(Kennel.section_id == section_id)
            .order_by(Kennel.identifier.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_transfer(self, transfer: FacilityTransfer) -> FacilityTransfer:
        self._session.add(transfer)
        await self._session.flush()
        return transfer

    async def get_transfer(self, transfer_id: uuid.UUID) -> FacilityTransfer | None:
        stmt = select(FacilityTransfer).where(FacilityTransfer.id == transfer_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_transfers(self) -> Sequence[FacilityTransfer]:
        stmt = select(FacilityTransfer).order_by(FacilityTransfer.created_at.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def create_care_log(self, care_log: DailyCareLog) -> DailyCareLog:
        self._session.add(care_log)
        await self._session.flush()
        return care_log

    async def list_care_logs_by_dog(self, dog_id: uuid.UUID) -> Sequence[DailyCareLog]:
        stmt = (
            select(DailyCareLog)
            .where(DailyCareLog.dog_id == dog_id)
            .order_by(DailyCareLog.feed_time.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_cleaning_log(self, log: KennelCleaningLog) -> KennelCleaningLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def list_cleaning_logs_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        kennel_id: uuid.UUID,
    ) -> tuple[Sequence[KennelCleaningLog], int]:
        stmt = select(KennelCleaningLog).where(KennelCleaningLog.kennel_id == kennel_id)

        valid_fields = {"cleaned_at", "sanitation_state_after", "created_at"}
        stmt = apply_sorting(stmt, sort, valid_fields)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_facilities_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: FacilityStatus | None = None,
        facility_type: FacilityType | None = None,
    ) -> tuple[Sequence[ShelterFacility], int]:
        stmt = select(ShelterFacility).where(ShelterFacility.deleted_at.is_(None))

        search_filter = build_search_filter(ShelterFacility, search_term, ("name", "address"))
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(ShelterFacility.status == status)
        if facility_type is not None:
            stmt = stmt.where(ShelterFacility.facility_type == facility_type)

        valid_fields = {
            "name", "total_capacity", "status",
            "facility_type", "created_at", "updated_at",
        }
        stmt = apply_sorting(stmt, sort, valid_fields)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_sections_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        facility_id: uuid.UUID | None = None,
        section_type: SectionType | None = None,
        search_term: str | None = None,
    ) -> tuple[Sequence[ShelterSection], int]:
        stmt = select(ShelterSection)

        if facility_id is not None:
            stmt = stmt.where(ShelterSection.facility_id == facility_id)

        if section_type is not None:
            stmt = stmt.where(ShelterSection.section_type == section_type)

        search_filter = build_search_filter(ShelterSection, search_term, ("name",))
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        valid_fields = {"name", "section_type", "capacity", "created_at"}
        stmt = apply_sorting(stmt, sort, valid_fields)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_kennels_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        section_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Kennel], int]:
        stmt = select(Kennel)

        if section_id is not None:
            stmt = stmt.where(Kennel.section_id == section_id)

        valid_fields = {"identifier", "capacity", "sanitation_state", "created_at"}
        stmt = apply_sorting(stmt, sort, valid_fields)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def soft_delete_facility(self, facility_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime
        stmt = (
            select(ShelterFacility)
            .where(ShelterFacility.id == facility_id, ShelterFacility.deleted_at.is_(None))
        )
        facility = (await self._session.execute(stmt)).scalar_one_or_none()
        if facility is None:
            return False
        facility.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def bulk_delete_facilities(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        stmt = (
            select(ShelterFacility)
            .where(ShelterFacility.id.in_(ids), ShelterFacility.deleted_at.is_(None))
        )
        facilities = (await self._session.execute(stmt)).scalars().all()
        for f in facilities:
            f.deleted_at = now
        await self._session.flush()
        return len(facilities)

    async def bulk_update_facility_status(
        self, ids: list[uuid.UUID], status: FacilityStatus
    ) -> int:
        stmt = (
            update(ShelterFacility)
            .where(ShelterFacility.id.in_(ids), ShelterFacility.deleted_at.is_(None))
            .values(status=status)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[attr-defined,no-any-return]
