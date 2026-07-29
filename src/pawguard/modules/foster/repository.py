"""Data access for the Foster Management module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.foster.models import FosterPlacement, FosterProfile, FosterStatus


class FosterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_profile(self, profile: FosterProfile) -> FosterProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_profile_by_id(self, profile_id: uuid.UUID) -> FosterProfile | None:
        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user))
            .where(FosterProfile.id == profile_id, FosterProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_profile_by_user_id(self, user_id: uuid.UUID) -> FosterProfile | None:
        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user))
            .where(FosterProfile.user_id == user_id, FosterProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_profiles(self, status: FosterStatus | None = None) -> Sequence[FosterProfile]:
        stmt = (
            select(FosterProfile)
            .options(selectinload(FosterProfile.user))
            .where(FosterProfile.deleted_at.is_(None))
            .order_by(FosterProfile.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(FosterProfile.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_placement(self, placement: FosterPlacement) -> FosterPlacement:
        self._session.add(placement)
        await self._session.flush()
        return placement

    async def get_placement_by_id(self, placement_id: uuid.UUID) -> FosterPlacement | None:
        stmt = select(FosterPlacement).where(FosterPlacement.id == placement_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_active_placement_for_dog(self, dog_id: uuid.UUID) -> FosterPlacement | None:
        stmt = select(FosterPlacement).where(
            FosterPlacement.dog_id == dog_id, FosterPlacement.is_active.is_(True)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
