"""DonationService: owns donor registers, contributions, and sponsorships (RULE-003)."""

import uuid
from datetime import UTC, datetime
from typing import Sequence

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.models import Donation, DonationStatus, DonationType, DonorProfile
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import DonationCreate, DonorProfileCreate


class DonationService:
    def __init__(self, repository: DonationRepository, dog_repo: DogRepository) -> None:
        self._repo = repository
        self._dog_repo = dog_repo

    async def register_donor(self, user_id: uuid.UUID, payload: DonorProfileCreate) -> DonorProfile:
        existing = await self._repo.get_donor_by_user_id(user_id)
        if existing is not None:
            raise ConflictError("You are already registered as a donor.")

        profile = DonorProfile(
            user_id=user_id,
            tax_identifier=payload.tax_identifier,
            notes=payload.notes,
        )
        return await self._repo.create_donor_profile(profile)

    async def get_or_create_donor(self, user_id: uuid.UUID) -> DonorProfile:
        donor = await self._repo.get_donor_by_user_id(user_id)
        if donor is None:
            # Silent registration
            donor = DonorProfile(user_id=user_id)
            await self._repo.create_donor_profile(donor)
        return donor

    async def make_donation(self, user_id: uuid.UUID, payload: DonationCreate) -> Donation:
        donor = await self.get_or_create_donor(user_id)

        if payload.dog_id is not None:
            dog = await self._dog_repo.get_by_id(payload.dog_id)
            if dog is None:
                raise NotFoundError("Dog profile not found.")

        # Simulate Payment Gateway reference generation
        tx_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        donation = Donation(
            donor_id=donor.id,
            dog_id=payload.dog_id,
            amount=payload.amount,
            currency=payload.currency,
            donation_type=payload.donation_type,
            status=DonationStatus.SUCCESS,  # Assume mock gateway succeeds immediately
            transaction_id=tx_id,
            notes=payload.notes,
        )
        await self._repo.create_donation(donation)
        res = await self._repo.get_donation_by_id(donation.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created donation record.")
        return res

    async def get_donation(self, donation_id: uuid.UUID) -> Donation:
        donation = await self._repo.get_donation_by_id(donation_id)
        if donation is None:
            raise NotFoundError("Donation record not found.")
        return donation

    async def list_donations_for_user(self, user_id: uuid.UUID) -> Sequence[Donation]:
        donor = await self._repo.get_donor_by_user_id(user_id)
        if donor is None:
            return []
        return await self._repo.get_donations_by_donor(donor.id)

    async def list_all_donations(self) -> Sequence[Donation]:
        return await self._repo.list_all_donations()
