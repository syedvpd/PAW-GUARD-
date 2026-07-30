"""Data access for the Dog Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.dog.models import DogProfile, DogStatus


class DogRepository:
    SEARCH_FIELDS = ("name", "breed", "registration_number", "microchip_id", "color")
    SORTABLE_FIELDS = {
        "name", "breed", "status", "created_at", "updated_at", "estimated_age", "weight",
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

    async def get_by_registration(self, reg_num: str) -> DogProfile | None:
        stmt = select(DogProfile).where(
            DogProfile.registration_number == reg_num, DogProfile.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: DogStatus | None = None,
        is_adoptable: bool | None = None,
        breed: str | None = None,
        gender: str | None = None,
        temperament: str | None = None,
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
        if gender is not None:
            stmt = stmt.where(DogProfile.gender == gender)
        if temperament is not None:
            stmt = stmt.where(DogProfile.temperament.ilike(f"%{temperament}%"))

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
