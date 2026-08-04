"""Data access for the Dog Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.dog.models import (
    DogActivityLog,
    DogBreedClassification,
    DogGender,
    DogProfile,
    DogStatus,
    DogWeightLog,
)
from pawguard.modules.shelter.models import ShelterFacility


class DogRepository:
    SEARCH_FIELDS = ("name", "breed", "registration_number", "microchip_id", "color")
    SORTABLE_FIELDS = {
        "name", "breed", "status", "created_at", "updated_at", "estimated_age",
        "age_months", "weight",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, dog: DogProfile) -> DogProfile:
        self._session.add(dog)
        await self._session.flush()
        await self._session.refresh(dog)
        return dog

    async def get_by_id(self, dog_id: uuid.UUID) -> DogProfile | None:
        stmt = select(DogProfile).where(DogProfile.id == dog_id, DogProfile.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_any_by_id(self, dog_id: uuid.UUID) -> DogProfile | None:
        """Fetch a dog regardless of soft-delete state.

        Used by the activity-stream reader so a dog's "permanent, audit-ready
        digital trail ... through final resolution" (PRR 3.4) stays readable
        even after the profile itself is soft-deleted.
        """
        stmt = select(DogProfile).where(DogProfile.id == dog_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id_for_update(self, dog_id: uuid.UUID) -> DogProfile | None:
        """Locks the dog row (SELECT ... FOR UPDATE) for the rest of the
        transaction - used to serialize concurrent adoption approvals on the
        same dog so the exclusivity check-then-act isn't a race condition."""
        from pawguard.core.config import get_settings
        from pawguard.core.constants import Environment

        stmt = select(DogProfile).where(
            DogProfile.id == dog_id, DogProfile.deleted_at.is_(None)
        )
        if get_settings().environment != Environment.TEST:
            stmt = stmt.with_for_update()

        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_registration(self, reg_num: str) -> DogProfile | None:
        stmt = select(DogProfile).where(
            DogProfile.registration_number == reg_num, DogProfile.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_microchip(self, microchip_id: str) -> DogProfile | None:
        """Find a non-deleted dog holding a given microchip id (UNIQUE column)."""
        stmt = select(DogProfile).where(
            DogProfile.microchip_id == microchip_id, DogProfile.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_duplicate_by_details(
        self,
        *,
        name: str,
        breed: str,
        gender: DogGender,
        color: str | None,
        distinctive_markers: str | None,
    ) -> DogProfile | None:
        """Find a non-deleted dog already carrying the same identifying
        details (PRR 3.4 duplicate-intake prevention).

        String comparisons are case-insensitive; only the identifying fields
        the caller supplied are matched - a NULL column matches only rows
        that are also NULL on that column, so an incomplete intake record
        never trips the guard against a fully identified dog."""
        stmt = select(DogProfile).where(
            DogProfile.deleted_at.is_(None),
            func.lower(DogProfile.name) == name.lower(),
            func.lower(DogProfile.breed) == breed.lower(),
            DogProfile.gender == gender,
        )
        if color:
            stmt = stmt.where(func.lower(DogProfile.color) == color.lower())
        else:
            stmt = stmt.where(DogProfile.color.is_(None))
        if distinctive_markers:
            stmt = stmt.where(
                func.lower(DogProfile.distinctive_markers) == distinctive_markers.lower()
            )
        else:
            stmt = stmt.where(DogProfile.distinctive_markers.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_by_kennel(
        self, kennel_id: uuid.UUID, exclude_dog_id: uuid.UUID | None = None
    ) -> int:
        stmt = select(func.count()).select_from(DogProfile).where(
            DogProfile.kennel_id == kennel_id, DogProfile.deleted_at.is_(None)
        )
        if exclude_dog_id is not None:
            stmt = stmt.where(DogProfile.id != exclude_dog_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def list_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: DogStatus | None = None,
        is_adoptable: bool | None = None,
        breed: str | None = None,
        breed_classification: DogBreedClassification | None = None,
        gender: str | None = None,
        temperament: str | None = None,
        min_age_months: int | None = None,
        max_age_months: int | None = None,
        min_weight: float | None = None,
        max_weight: float | None = None,
        location: str | None = None,
    ) -> tuple[Sequence[DogProfile], int]:
        stmt = select(DogProfile).where(DogProfile.deleted_at.is_(None))

        search_filter = build_search_filter(DogProfile, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(DogProfile.status == status)
        if is_adoptable is not None:
            stmt = stmt.where(DogProfile.is_adoptable == is_adoptable)
        if breed is not None:
            stmt = stmt.where(DogProfile.breed.ilike(f"%{breed}%"))
        if breed_classification is not None:
            stmt = stmt.where(DogProfile.breed_classification == breed_classification)
        if gender is not None:
            stmt = stmt.where(DogProfile.gender == gender)
        if temperament is not None:
            stmt = stmt.where(DogProfile.temperament == temperament)

        # Public adoption-directory filters (PRR 3.1.4: age, size, location).
        if min_age_months is not None:
            stmt = stmt.where(DogProfile.age_months >= min_age_months)
        if max_age_months is not None:
            stmt = stmt.where(DogProfile.age_months <= max_age_months)
        if min_weight is not None:
            stmt = stmt.where(DogProfile.weight >= min_weight)
        if max_weight is not None:
            stmt = stmt.where(DogProfile.weight <= max_weight)
        if location:
            # Free-text match on the holding shelter facility's name/address
            # (JOIN is safe: shelter_facility_id is a nullable FK, so dogs
            # without a facility are excluded only when the filter is active).
            stmt = stmt.join(
                ShelterFacility, DogProfile.shelter_facility_id == ShelterFacility.id
            ).where(
                or_(
                    ShelterFacility.name.ilike(f"%{location}%"),
                    ShelterFacility.address.ilike(f"%{location}%"),
                )
            )

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_by_ids(self, ids: list[uuid.UUID]) -> Sequence[DogProfile]:
        stmt = select(DogProfile).where(DogProfile.id.in_(ids), DogProfile.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalars().all()

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(DogProfile.status, func.count()).where(
            DogProfile.deleted_at.is_(None)
        ).group_by(DogProfile.status)
        rows = (await self._session.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}

    async def bulk_update_status(self, ids: list[uuid.UUID], status: DogStatus) -> int:
        from sqlalchemy import update
        stmt = (
            update(DogProfile)
            .where(DogProfile.id.in_(ids), DogProfile.deleted_at.is_(None))
            .values(status=status)
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def bulk_soft_delete(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        from sqlalchemy import update
        stmt = (
            update(DogProfile)
            .where(DogProfile.id.in_(ids), DogProfile.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    # --- Activity stream (PRR 3.4: immutable chronological trail) ---

    async def create_activity(self, log: DogActivityLog) -> DogActivityLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def list_activity_by_dog(
        self, dog_id: uuid.UUID
    ) -> Sequence[DogActivityLog]:
        stmt = (
            select(DogActivityLog)
            .where(DogActivityLog.dog_id == dog_id)
            .order_by(DogActivityLog.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    # --- Weight history (PRR 3.4: append-only measurement log) ---

    async def create_weight_log(self, log: DogWeightLog) -> DogWeightLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def list_weight_logs(
        self, dog_id: uuid.UUID
    ) -> Sequence[DogWeightLog]:
        stmt = (
            select(DogWeightLog)
            .where(DogWeightLog.dog_id == dog_id)
            .order_by(DogWeightLog.measured_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()
