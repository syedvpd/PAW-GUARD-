"""Data access for the Shelter & Capacity Management module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.shelter.models import (
    DailyCareLog,
    FacilityTransfer,
    Kennel,
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
        stmt = select(ShelterFacility).where(ShelterFacility.id == facility_id, ShelterFacility.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_facilities(self) -> Sequence[ShelterFacility]:
        stmt = select(ShelterFacility).where(ShelterFacility.deleted_at.is_(None)).order_by(ShelterFacility.name.asc())
        return (await self._session.execute(stmt)).scalars().all()

    async def create_section(self, section: ShelterSection) -> ShelterSection:
        self._session.add(section)
        await self._session.flush()
        return section

    async def get_section(self, section_id: uuid.UUID) -> ShelterSection | None:
        stmt = select(ShelterSection).where(ShelterSection.id == section_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_sections_by_facility(self, facility_id: uuid.UUID) -> Sequence[ShelterSection]:
        stmt = select(ShelterSection).where(ShelterSection.facility_id == facility_id).order_by(ShelterSection.name.asc())
        return (await self._session.execute(stmt)).scalars().all()

    async def create_kennel(self, kennel: Kennel) -> Kennel:
        self._session.add(kennel)
        await self._session.flush()
        return kennel

    async def get_kennel(self, kennel_id: uuid.UUID) -> Kennel | None:
        stmt = select(Kennel).where(Kennel.id == kennel_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_kennels_by_section(self, section_id: uuid.UUID) -> Sequence[Kennel]:
        stmt = select(Kennel).where(Kennel.section_id == section_id).order_by(Kennel.identifier.asc())
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
        stmt = select(DailyCareLog).where(DailyCareLog.dog_id == dog_id).order_by(DailyCareLog.feed_time.desc())
        return (await self._session.execute(stmt)).scalars().all()
