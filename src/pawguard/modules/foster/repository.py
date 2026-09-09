"""Data access for the Foster Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.auth.models import User
from pawguard.modules.foster.models import (
    FosterPlacement,
    FosterPlacementStatus,
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
        filters = [FosterProfile.deleted_at.is_(None)]
        search_filter = build_search_filter(FosterProfile, search_term, self.PROFILE_SEARCH_FIELDS)
        if search_filter is not None:
            filters.append(search_filter)

        if status is not None:
            filters.append(FosterProfile.status == status)
        if is_available is not None:
            filters.append(FosterProfile.is_available == is_available)

        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user).selectinload(User.roles))
            .where(*filters)
        )
        stmt = apply_sorting(stmt, sort, self.PROFILE_SORTABLE_FIELDS)
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        if page.page == 1 and len(results) < page.limit:
            total = len(results)
        else:
            count_stmt = select(func.count(FosterProfile.id)).where(*filters)
            total = (await self._session.execute(count_stmt)).scalar_one()

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
            .options(
                selectinload(FosterPlacement.foster)
                .selectinload(FosterProfile.user)
                .selectinload(User.roles),
                selectinload(FosterPlacement.dog),
            )
            .where(FosterPlacement.id == placement_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_active_placement_for_dog(self, dog_id: uuid.UUID) -> FosterPlacement | None:
        stmt = (
            select(FosterPlacement)
            .options(
                selectinload(FosterPlacement.foster)
                .selectinload(FosterProfile.user)
                .selectinload(User.roles),
                selectinload(FosterPlacement.dog),
            )
            .where(FosterPlacement.dog_id == dog_id, FosterPlacement.is_active.is_(True))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_placements_by_foster_id(self, foster_id: uuid.UUID) -> Sequence[FosterPlacement]:
        stmt = (
            select(FosterPlacement)
            .options(
                selectinload(FosterPlacement.dog),
                selectinload(FosterPlacement.foster)
                .selectinload(FosterProfile.user)
                .selectinload(User.roles),
            )
            .where(FosterPlacement.foster_id == foster_id)
            .order_by(FosterPlacement.placed_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def paginate_placements(
        self,
        page: PageParams,
        sort: SortParams,
        is_active: bool | None = None,
        status: FosterPlacementStatus | None = None,
        foster_id: uuid.UUID | None = None,
        dog_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[FosterPlacement], int]:
        filters = []
        if is_active is not None:
            filters.append(FosterPlacement.is_active == is_active)
        if status is not None:
            filters.append(FosterPlacement.status == status)
        if foster_id is not None:
            filters.append(FosterPlacement.foster_id == foster_id)
        if dog_id is not None:
            filters.append(FosterPlacement.dog_id == dog_id)

        stmt = select(FosterPlacement).options(
            selectinload(FosterPlacement.dog),
            selectinload(FosterPlacement.foster)
            .selectinload(FosterProfile.user)
            .selectinload(User.roles),
        )
        if filters:
            stmt = stmt.where(*filters)
        stmt = stmt.order_by(FosterPlacement.placed_at.desc())
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        if page.page == 1 and len(results) < page.limit:
            total = len(results)
        else:
            count_stmt = select(func.count(FosterPlacement.id))
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = (await self._session.execute(count_stmt)).scalar_one()

        return results, total

    async def get_foster_stats(self) -> dict[str, Any]:
        stmt = select(
            func.count(FosterPlacement.id).label("total_placements"),
            func.count(FosterPlacement.id)
            .filter(FosterPlacement.is_active.is_(True))
            .label("active_placements"),
            func.count(FosterPlacement.id)
            .filter(FosterPlacement.status == FosterPlacementStatus.RETURNED)
            .label("returned_placements"),
            func.count(FosterPlacement.id)
            .filter(FosterPlacement.status == FosterPlacementStatus.CONVERTED_TO_ADOPT)
            .label("converted_placements"),
        )
        placement_row = (await self._session.execute(stmt)).one()

        p_stmt = select(
            func.count(FosterProfile.id)
            .filter(FosterProfile.deleted_at.is_(None))
            .label("total_fosters"),
            func.count(FosterProfile.id)
            .filter(
                FosterProfile.deleted_at.is_(None), FosterProfile.status == FosterStatus.APPROVED
            )
            .label("approved_fosters"),
            func.count(FosterProfile.id)
            .filter(
                FosterProfile.deleted_at.is_(None),
                FosterProfile.status == FosterStatus.APPROVED,
                FosterProfile.is_available.is_(True),
            )
            .label("available_fosters"),
            func.count(FosterProfile.id)
            .filter(
                FosterProfile.deleted_at.is_(None), FosterProfile.status == FosterStatus.APPLIED
            )
            .label("pending_applications"),
            func.count(FosterProfile.id)
            .filter(
                FosterProfile.deleted_at.is_(None), FosterProfile.status == FosterStatus.REJECTED
            )
            .label("rejected_fosters"),
            func.count(FosterProfile.id)
            .filter(
                FosterProfile.deleted_at.is_(None), FosterProfile.status == FosterStatus.INACTIVE
            )
            .label("inactive_fosters"),
            func.coalesce(
                func.sum(FosterProfile.max_capacity).filter(
                    FosterProfile.deleted_at.is_(None),
                    FosterProfile.status == FosterStatus.APPROVED,
                ),
                0,
            ).label("total_capacity"),
        )
        profile_row = (await self._session.execute(p_stmt)).one()

        return {
            "total": placement_row.total_placements or 0,
            "active": placement_row.active_placements or 0,
            "total_placements": placement_row.total_placements or 0,
            "active_placements": placement_row.active_placements or 0,
            "returned_placements": placement_row.returned_placements or 0,
            "converted_placements": placement_row.converted_placements or 0,
            "total_fosters": profile_row.total_fosters or 0,
            "total_profiles": profile_row.total_fosters or 0,
            "approved_fosters": profile_row.approved_fosters or 0,
            "available_fosters": profile_row.available_fosters or 0,
            "available": profile_row.available_fosters or 0,
            "pending_applications": profile_row.pending_applications or 0,
            "pending_fosters": profile_row.pending_applications or 0,
            "rejected_fosters": profile_row.rejected_fosters or 0,
            "inactive_fosters": profile_row.inactive_fosters or 0,
            "total_capacity": int(profile_row.total_capacity or 0),
        }

    async def list_profiles_by_ids(self, ids: list[uuid.UUID]) -> Sequence[FosterProfile]:
        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user).selectinload(User.roles))
            .where(FosterProfile.id.in_(ids), FosterProfile.deleted_at.is_(None))
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
