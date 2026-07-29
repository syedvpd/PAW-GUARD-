"""Data access for the Donation Management module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.donation.models import Donation, DonorProfile


class DonationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_donor_profile(self, profile: DonorProfile) -> DonorProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_donor_by_id(self, donor_id: uuid.UUID) -> DonorProfile | None:
        stmt = (
            select(DonorProfile)
            .options(selectinload(DonorProfile.user))
            .where(DonorProfile.id == donor_id, DonorProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_donor_by_user_id(self, user_id: uuid.UUID) -> DonorProfile | None:
        stmt = (
            select(DonorProfile)
            .options(selectinload(DonorProfile.user))
            .where(DonorProfile.user_id == user_id, DonorProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_donation(self, donation: Donation) -> Donation:
        self._session.add(donation)
        await self._session.flush()
        return donation

    async def get_donation_by_id(self, donation_id: uuid.UUID) -> Donation | None:
        stmt = (
            select(Donation)
            .options(selectinload(Donation.donor), selectinload(Donation.dog))
            .where(Donation.id == donation_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_donations_by_donor(self, donor_id: uuid.UUID) -> Sequence[Donation]:
        stmt = (
            select(Donation)
            .options(selectinload(Donation.dog))
            .where(Donation.donor_id == donor_id)
            .order_by(Donation.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_all_donations(self) -> Sequence[Donation]:
        stmt = (
            select(Donation)
            .options(selectinload(Donation.donor), selectinload(Donation.dog))
            .order_by(Donation.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()
