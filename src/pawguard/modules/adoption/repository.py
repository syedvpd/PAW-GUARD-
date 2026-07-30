"""Data access for the Adoption Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus


class AdoptionRepository:
    SEARCH_FIELDS = (
        "vetting_officer_notes",
        "home_inspection_notes",
        "residential_status",
    )
    SORTABLE_FIELDS = {
        "status", "created_at", "updated_at", "completed_at",
        "residential_status", "household_members_count",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, app: AdoptionApplication) -> AdoptionApplication:
        self._session.add(app)
        await self._session.flush()
        return app

    async def get_by_id(self, app_id: uuid.UUID) -> AdoptionApplication | None:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter)
            )
            .where(AdoptionApplication.id == app_id, AdoptionApplication.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_by_dog(self, dog_id: uuid.UUID) -> Sequence[AdoptionApplication]:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter)
            )
            .where(AdoptionApplication.dog_id == dog_id, AdoptionApplication.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_by_adopter(self, adopter_id: uuid.UUID) -> Sequence[AdoptionApplication]:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter)
            )
            .where(
                AdoptionApplication.adopter_id == adopter_id,
                AdoptionApplication.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: AdoptionStatus | None = None,
        dog_id: uuid.UUID | None = None,
        adopter_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[AdoptionApplication], int]:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter)
            )
            .where(AdoptionApplication.deleted_at.is_(None))
        )

        search_filter = build_search_filter(AdoptionApplication, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(AdoptionApplication.status == status)
        if dog_id is not None:
            stmt = stmt.where(AdoptionApplication.dog_id == dog_id)
        if adopter_id is not None:
            stmt = stmt.where(AdoptionApplication.adopter_id == adopter_id)

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_by_ids(self, ids: list[uuid.UUID]) -> Sequence[AdoptionApplication]:
        stmt = (
            select(AdoptionApplication)
            .where(AdoptionApplication.id.in_(ids), AdoptionApplication.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalars().all()

    # Statuses that exclusively lock a dog against other applications. Per the
    # PRR, exclusivity starts once an application reaches home-inspection
    # approval (HOME_CHECK), not just final APPROVED - two applicants must
    # not both be mid-inspection for the same dog at once.
    LOCKING_STATUSES = (
        AdoptionStatus.HOME_CHECK, AdoptionStatus.APPROVED, AdoptionStatus.COMPLETED,
    )

    async def get_approved_application_for_dog(
        self, dog_id: uuid.UUID
    ) -> AdoptionApplication | None:
        stmt = (
            select(AdoptionApplication)
            .where(
                AdoptionApplication.dog_id == dog_id,
                AdoptionApplication.status.in_(self.LOCKING_STATUSES),
                AdoptionApplication.deleted_at.is_(None)
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def bulk_update_status(self, ids: list[uuid.UUID], status: AdoptionStatus) -> int:
        from sqlalchemy import update
        stmt = (
            update(AdoptionApplication)
            .where(AdoptionApplication.id.in_(ids), AdoptionApplication.deleted_at.is_(None))
            .values(status=status)
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]
