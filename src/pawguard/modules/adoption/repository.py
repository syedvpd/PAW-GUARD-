"""Data access for the Adoption Management module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus


class AdoptionRepository:
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
            .where(AdoptionApplication.adopter_id == adopter_id, AdoptionApplication.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_all(self, status: AdoptionStatus | None = None) -> Sequence[AdoptionApplication]:
        stmt = (
            select(AdoptionApplication)
            .options(
                selectinload(AdoptionApplication.dog),
                selectinload(AdoptionApplication.adopter)
            )
            .where(AdoptionApplication.deleted_at.is_(None))
            .order_by(AdoptionApplication.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(AdoptionApplication.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_approved_application_for_dog(self, dog_id: uuid.UUID) -> AdoptionApplication | None:
        stmt = (
            select(AdoptionApplication)
            .where(
                AdoptionApplication.dog_id == dog_id,
                AdoptionApplication.status == AdoptionStatus.APPROVED,
                AdoptionApplication.deleted_at.is_(None)
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
