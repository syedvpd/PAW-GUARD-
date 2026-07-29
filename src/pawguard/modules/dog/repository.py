"""Data access for the Dog Management module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.dog.models import DogProfile, DogStatus


class DogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, dog: DogProfile) -> DogProfile:
        self._session.add(dog)
        await self._session.flush()
        return dog

    async def get_by_id(self, dog_id: uuid.UUID) -> DogProfile | None:
        stmt = select(DogProfile).where(DogProfile.id == dog_id, DogProfile.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_registration(self, reg_num: str) -> DogProfile | None:
        stmt = select(DogProfile).where(DogProfile.registration_number == reg_num, DogProfile.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_all(self, status: DogStatus | None = None, is_adoptable: bool | None = None) -> Sequence[DogProfile]:
        stmt = select(DogProfile).where(DogProfile.deleted_at.is_(None)).order_by(DogProfile.created_at.desc())
        if status is not None:
            stmt = stmt.where(DogProfile.status == status)
        if is_adoptable is not None:
            stmt = stmt.where(DogProfile.is_adoptable == is_adoptable)
        return (await self._session.execute(stmt)).scalars().all()
