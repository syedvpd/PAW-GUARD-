"""Data access for the Shelter & Capacity Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy import literal as sa_literal
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.shelter.models import (
    DailyCareLog,
    FacilityStatus,
    FacilityTransfer,
    FacilityType,
    Kennel,
    KennelCleaningLog,
    KennelSanitationState,
    SectionType,
    ShelterFacility,
    ShelterSection,
    ShelterVetRequest,
    ShelterVetRequestStatus,
    TransferStatus,
)


class ShelterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_facility(self, facility: ShelterFacility) -> ShelterFacility:
        self._session.add(facility)
        await self._session.flush()
        return facility

    async def get_facility(self, facility_id: uuid.UUID) -> ShelterFacility | None:
        stmt = select(ShelterFacility).where(
            ShelterFacility.id == facility_id, ShelterFacility.deleted_at.is_(None)
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

    async def find_nearby_facilities(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> Sequence[tuple[ShelterFacility, float]]:
        """Return facilities (with a known location) within ``radius_km`` of the
        given coordinate, nearest first, plus each facility's distance in km.

        Uses the haversine great-circle distance computed in SQL so no PostGIS
        extension is required on the managed Postgres hosting.
        """
        lat1 = func.radians(sa_literal(latitude))
        lng1 = func.radians(sa_literal(longitude))
        lat2 = func.radians(ShelterFacility.latitude)
        lng2 = func.radians(ShelterFacility.longitude)

        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a_expr = func.pow(func.sin(dlat / 2), 2) + func.cos(lat1) * func.cos(lat2) * func.pow(
            func.sin(dlng / 2), 2
        )
        distance_km = (2 * sa_literal(6371.0) * func.asin(func.sqrt(a_expr))).label("distance_km")

        stmt = (
            select(ShelterFacility, distance_km)
            .where(
                ShelterFacility.deleted_at.is_(None),
                ShelterFacility.latitude.is_not(None),
                ShelterFacility.longitude.is_not(None),
                distance_km <= radius_km,
            )
            .order_by(distance_km.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]

    async def list_adoptable_dogs_by_facilities(
        self,
        facility_ids: Sequence[uuid.UUID],
    ) -> Sequence[DogProfile]:
        if not facility_ids:
            return []
        stmt = (
            select(DogProfile)
            .where(
                DogProfile.shelter_facility_id.in_(facility_ids),
                DogProfile.is_adoptable.is_(True),
                DogProfile.deleted_at.is_(None),
            )
            .order_by(DogProfile.name.asc())
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
            select(Kennel).where(Kennel.section_id == section_id).order_by(Kennel.identifier.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def count_occupied_in_section(
        self, section_id: uuid.UUID, exclude_dog_id: uuid.UUID | None = None
    ) -> int:
        """Dogs currently housed in any kennel of this section — the section-level
        occupancy the over-capacity alert (RULE) is measured against, distinct
        from a single kennel's own capacity."""
        filters = [Kennel.section_id == section_id, DogProfile.deleted_at.is_(None)]
        if exclude_dog_id is not None:
            filters.append(DogProfile.id != exclude_dog_id)
        stmt = (
            select(func.count(DogProfile.id))
            .join(Kennel, Kennel.id == DogProfile.kennel_id)
            .where(*filters)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def find_available_kennel_by_section_type(
        self, section_type: SectionType, facility_id: uuid.UUID | None = None
    ) -> Kennel | None:
        """First Open + Clean kennel in an active facility's section of this
        type — used by the rescue ADMITTED flow to auto-reserve a Quarantine
        kennel without staff having to pick one manually."""
        from sqlalchemy import and_

        stmt = (
            select(Kennel)
            .join(ShelterSection, ShelterSection.id == Kennel.section_id)
            .join(ShelterFacility, ShelterFacility.id == ShelterSection.facility_id)
            .outerjoin(
                DogProfile,
                and_(DogProfile.kennel_id == Kennel.id, DogProfile.deleted_at.is_(None)),
            )
            .where(
                ShelterSection.section_type == section_type,
                Kennel.sanitation_state == KennelSanitationState.CLEAN,
                DogProfile.id.is_(None),
                ShelterFacility.status == FacilityStatus.ACTIVE,
                ShelterFacility.deleted_at.is_(None),
            )
        )
        if facility_id is not None:
            stmt = stmt.where(ShelterFacility.id == facility_id)
        stmt = stmt.order_by(Kennel.identifier.asc()).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_active_transfer_for_kennel(self, kennel_id: uuid.UUID) -> FacilityTransfer | None:
        """The transfer (if any) currently soft-locking this kennel as a
        destination — a second transfer targeting the same kennel must be
        rejected, not silently overwrite the reservation."""
        stmt = select(FacilityTransfer).where(
            FacilityTransfer.destination_kennel_id == kennel_id,
            FacilityTransfer.status.in_([TransferStatus.PENDING, TransferStatus.IN_TRANSIT]),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

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
        count_stmt = select(func.count(KennelCleaningLog.id)).where(
            KennelCleaningLog.kennel_id == kennel_id
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = select(KennelCleaningLog).where(KennelCleaningLog.kennel_id == kennel_id)
        valid_fields = {"cleaned_at", "sanitation_state_after", "created_at"}
        stmt = apply_sorting(stmt, sort, valid_fields)
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
        filters = [ShelterFacility.deleted_at.is_(None)]

        search_filter = build_search_filter(ShelterFacility, search_term, ("name", "address"))
        if search_filter is not None:
            filters.append(search_filter)

        if status is not None:
            filters.append(ShelterFacility.status == status)
        if facility_type is not None:
            filters.append(ShelterFacility.facility_type == facility_type)

        stmt = select(ShelterFacility).where(*filters)
        valid_fields = {
            "name",
            "total_capacity",
            "status",
            "facility_type",
            "created_at",
            "updated_at",
        }
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        if page_params.page == 1 and len(results) < page_params.limit:
            total = len(results)
        else:
            count_stmt = select(func.count(ShelterFacility.id)).where(*filters)
            total = (await self._session.execute(count_stmt)).scalar_one()

        return results, total

    async def list_sections_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        facility_id: uuid.UUID | None = None,
        section_type: SectionType | None = None,
        search_term: str | None = None,
    ) -> tuple[Sequence[ShelterSection], int]:
        filters = []
        if facility_id is not None:
            filters.append(ShelterSection.facility_id == facility_id)

        if section_type is not None:
            filters.append(ShelterSection.section_type == section_type)

        search_filter = build_search_filter(ShelterSection, search_term, ("name",))
        if search_filter is not None:
            filters.append(search_filter)

        count_stmt = select(func.count(ShelterSection.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = select(ShelterSection)
        if filters:
            stmt = stmt.where(*filters)
        valid_fields = {"name", "section_type", "capacity", "created_at"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_kennels_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        section_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Kennel], int]:
        count_stmt = select(func.count(Kennel.id))
        if section_id is not None:
            count_stmt = count_stmt.where(Kennel.section_id == section_id)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = select(Kennel)
        if section_id is not None:
            stmt = stmt.where(Kennel.section_id == section_id)

        valid_fields = {"identifier", "capacity", "sanitation_state", "created_at"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def soft_delete_facility(self, facility_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime

        stmt = select(ShelterFacility).where(
            ShelterFacility.id == facility_id, ShelterFacility.deleted_at.is_(None)
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
        stmt = select(ShelterFacility).where(
            ShelterFacility.id.in_(ids), ShelterFacility.deleted_at.is_(None)
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

    async def create_vet_request(self, request: ShelterVetRequest) -> ShelterVetRequest:
        self._session.add(request)
        await self._session.flush()
        return request

    async def get_vet_request(self, request_id: uuid.UUID) -> ShelterVetRequest | None:
        stmt = select(ShelterVetRequest).where(ShelterVetRequest.id == request_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_active_vet_request_for_dog(self, dog_id: uuid.UUID) -> ShelterVetRequest | None:
        """Find an existing active (pending/in_progress) vet request for a dog."""
        stmt = select(ShelterVetRequest).where(
            ShelterVetRequest.dog_id == dog_id,
            ShelterVetRequest.status.in_(
                [ShelterVetRequestStatus.PENDING, ShelterVetRequestStatus.IN_PROGRESS]
            ),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_vet_requests_for_vet(
        self,
        vet_id: uuid.UUID,
        status: ShelterVetRequestStatus | None = None,
    ) -> Sequence[ShelterVetRequest]:
        """List vet requests assigned to a specific veterinarian."""
        stmt = select(ShelterVetRequest).where(ShelterVetRequest.vet_id == vet_id)
        if status is not None:
            stmt = stmt.where(ShelterVetRequest.status == status)
        stmt = stmt.order_by(ShelterVetRequest.created_at.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def list_vet_requests_for_facility(
        self,
        facility_id: uuid.UUID,
        status: ShelterVetRequestStatus | None = None,
    ) -> Sequence[ShelterVetRequest]:
        """List all vet requests for a specific shelter facility."""
        stmt = select(ShelterVetRequest).where(ShelterVetRequest.shelter_facility_id == facility_id)
        if status is not None:
            stmt = stmt.where(ShelterVetRequest.status == status)
        stmt = stmt.order_by(ShelterVetRequest.created_at.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def update_vet_request_status(
        self,
        request_id: uuid.UUID,
        new_status: ShelterVetRequestStatus,
    ) -> ShelterVetRequest | None:
        stmt = select(ShelterVetRequest).where(ShelterVetRequest.id == request_id)
        request = (await self._session.execute(stmt)).scalar_one_or_none()
        if request is None:
            return None
        request.status = new_status
        await self._session.flush()
        return request
