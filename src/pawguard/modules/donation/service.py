"""DonationService: owns donor registers, contributions, and sponsorships (RULE-003)."""

import uuid

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.models import Donation, DonationStatus, DonorProfile
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import (
    DonationCreate,
    DonationResponse,
    DonorProfileCreate,
    DonorProfileResponse,
    DonorProfileUpdate,
)


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
            donor = DonorProfile(user_id=user_id)
            await self._repo.create_donor_profile(donor)
        return donor

    async def make_donation(self, user_id: uuid.UUID, payload: DonationCreate) -> Donation:
        donor = await self.get_or_create_donor(user_id)

        if payload.dog_id is not None:
            dog = await self._dog_repo.get_by_id(payload.dog_id)
            if dog is None:
                raise NotFoundError("Dog profile not found.")

        tx_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        donation = Donation(
            donor_id=donor.id,
            dog_id=payload.dog_id,
            amount=payload.amount,
            currency=payload.currency,
            donation_type=payload.donation_type,
            status=DonationStatus.SUCCESS,
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

    async def list_donations_for_user(self, user_id: uuid.UUID) -> list[Donation]:
        donor = await self._repo.get_donor_by_user_id(user_id)
        if donor is None:
            return []
        return list(await self._repo.get_donations_by_donor(donor.id))

    async def update_donor(self, donor_id: uuid.UUID, payload: DonorProfileUpdate) -> DonorProfile:
        donor = await self._repo.get_donor_by_id(donor_id)
        if donor is None:
            raise NotFoundError("Donor profile not found.")
        updated = await self._repo.update_donor_profile(
            donor_id,
            **payload.model_dump(exclude_unset=True),
        )
        if updated is None:
            raise NotFoundError("Donor profile not found after update.")
        return updated

    async def update_donation_status(
        self, donation_id: uuid.UUID, status: DonationStatus
    ) -> Donation:
        donation = await self._repo.get_donation_by_id(donation_id)
        if donation is None:
            raise NotFoundError("Donation record not found.")
        updated = await self._repo.update_donation_status(donation_id, status)
        if updated is None:
            raise NotFoundError("Failed to update donation status.")
        return updated

    async def soft_delete_donor(self, donor_id: uuid.UUID) -> None:
        donor = await self._repo.get_donor_by_id(donor_id)
        if donor is None:
            raise NotFoundError("Donor profile not found.")
        await self._repo.soft_delete_donor(donor_id)

    async def list_donations_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        donation_type: str | None = None,
        status: DonationStatus | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> PaginatedResponse[DonationResponse]:
        results, total = await self._repo.paginate_donations(
            page=page,
            sort=sort,
            search_term=search_term,
            donation_type=donation_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        return PaginatedResponse(
            data=[DonationResponse.model_validate(d) for d in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def list_donors_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
    ) -> PaginatedResponse[DonorProfileResponse]:
        results, total = await self._repo.paginate_donors(
            page=page,
            sort=sort,
            search_term=search_term,
        )
        return PaginatedResponse(
            data=[DonorProfileResponse.model_validate(d) for d in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def bulk_update_status(
        self,
        ids: list[uuid.UUID],
        status: DonationStatus,
    ) -> int:
        return await self._repo.bulk_update_donation_status(ids, status)

    async def bulk_soft_delete(
        self,
        ids: list[uuid.UUID],
    ) -> int:
        return await self._repo.bulk_soft_delete_donors(ids)
