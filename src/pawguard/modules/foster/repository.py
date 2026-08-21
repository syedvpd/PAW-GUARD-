"""Data access for the Foster Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.auth.models import User
from pawguard.modules.foster.models import (
    FosterPlacement,
    FosterProfile,
    FosterProgressLog,
    FosterStatus,
    FosterSupplyDispatch,
)


class FosterRepository:
    PROFILE_SEARCH_FIELDS = ("preferences", "notes")
    PROFILE_SORTABLE_FIELDS = {
        "status",
        "max_capacity",
        "active_count",
        "is_available",
        "created_at",
        "updated_at",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_profile(self, profile: FosterProfile) -> FosterProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_profile_by_id(self, profile_id: uuid.UUID) -> FosterProfile | None:
        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user).selectinload(User.roles))
            .where(FosterProfile.id == profile_id, FosterProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_profile_by_id_for_update(self, profile_id: uuid.UUID) -> FosterProfile | None:
        """Return a foster profile under a row lock for placement allocation."""
        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user).selectinload(User.roles))
            .where(FosterProfile.id == profile_id, FosterProfile.deleted_at.is_(None))
            .with_for_update()
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_profile_by_user_id(self, user_id: uuid.UUID) -> FosterProfile | None:
        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user).selectinload(User.roles))
            .where(FosterProfile.user_id == user_id, FosterProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def paginate_profiles(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: FosterStatus | None = None,
        is_available: bool | None = None,
    ) -> tuple[Sequence[FosterProfile], int]:
        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user).selectinload(User.roles))
            .where(FosterProfile.deleted_at.is_(None))
        )
        search_filter = build_search_filter(FosterProfile, search_term, self.PROFILE_SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if status is not None:
            stmt = stmt.where(FosterProfile.status == status)
        if is_available is not None:
            stmt = stmt.where(FosterProfile.is_available == is_available)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = apply_sorting(stmt, sort, self.PROFILE_SORTABLE_FIELDS)
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def soft_delete_profile(self, profile_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime

        stmt = (
            update(FosterProfile)
            .where(FosterProfile.id == profile_id, FosterProfile.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]

    async def create_placement(self, placement: FosterPlacement) -> FosterPlacement:
        self._session.add(placement)
        await self._session.flush()
        return placement

    async def get_placement_by_id(self, placement_id: uuid.UUID) -> FosterPlacement | None:
        stmt = (
            select(FosterPlacement)
            .options(selectinload(FosterPlacement.foster))
            .where(FosterPlacement.id == placement_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_active_placement_for_dog(self, dog_id: uuid.UUID) -> FosterPlacement | None:
        stmt = select(FosterPlacement).where(
            FosterPlacement.dog_id == dog_id, FosterPlacement.is_active.is_(True)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_placements_by_foster_id(self, foster_id: uuid.UUID) -> Sequence[FosterPlacement]:
        stmt = (
            select(FosterPlacement)
            .options(selectinload(FosterPlacement.dog))
            .where(FosterPlacement.foster_id == foster_id)
            .order_by(FosterPlacement.placed_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_profiles_by_ids(self, ids: list[uuid.UUID]) -> Sequence[FosterProfile]:
        stmt = select(FosterProfile).where(
            FosterProfile.id.in_(ids), FosterProfile.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def bulk_soft_delete_profiles(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        stmt = (
            update(FosterProfile)
            .where(FosterProfile.id.in_(ids), FosterProfile.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def create_progress_log(self, log: FosterProgressLog) -> FosterProgressLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def get_progress_logs_for_placement(
        self, placement_id: uuid.UUID
    ) -> Sequence[FosterProgressLog]:
        stmt = (
            select(FosterProgressLog)
            .where(FosterProgressLog.placement_id == placement_id)
            .order_by(FosterProgressLog.logged_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_supply_dispatch(self, dispatch: FosterSupplyDispatch) -> FosterSupplyDispatch:
        self._session.add(dispatch)
        await self._session.flush()
        return dispatch

    async def get_supply_dispatches_for_placement(
        self, placement_id: uuid.UUID
    ) -> Sequence[FosterSupplyDispatch]:
        stmt = (
            select(FosterSupplyDispatch)
            .where(FosterSupplyDispatch.placement_id == placement_id)
            .order_by(FosterSupplyDispatch.dispatched_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_recent_progress_logs_for_placement(
        self, placement_id: uuid.UUID, limit: int = 5
    ) -> Sequence[FosterProgressLog]:
        stmt = (
            select(FosterProgressLog)
            .where(FosterProgressLog.placement_id == placement_id)
            .order_by(FosterProgressLog.logged_at.desc())
            .limit(limit)
        )
        return (await self._session.execute(stmt)).scalars().all()
