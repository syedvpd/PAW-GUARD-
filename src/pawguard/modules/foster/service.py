"""FosterService: owns foster applications, home availability, and placements (RULE-003)."""

import uuid
from datetime import UTC, datetime
from typing import Sequence

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.foster.models import FosterPlacement, FosterProfile, FosterStatus
from pawguard.modules.foster.repository import FosterRepository
from pawguard.modules.foster.schemas import FosterPlacementCreate, FosterProfileCreate, FosterProfileUpdate


class FosterService:
    def __init__(self, repository: FosterRepository, dog_repo: DogRepository) -> None:
        self._repo = repository
        self._dog_repo = dog_repo

    async def apply_to_foster(self, user_id: uuid.UUID, payload: FosterProfileCreate) -> FosterProfile:
        existing = await self._repo.get_profile_by_user_id(user_id)
        if existing is not None:
            raise ConflictError("You have already applied or registered as a foster home.")

        profile = FosterProfile(
            user_id=user_id,
            preferences=payload.preferences,
            max_capacity=payload.max_capacity,
            status=FosterStatus.APPLIED,
            is_available=True,
        )
        await self._repo.create_profile(profile)
        res = await self._repo.get_profile_by_id(profile.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created foster profile.")
        return res

    async def update_profile(
        self, profile_id: uuid.UUID, payload: FosterProfileUpdate
    ) -> FosterProfile:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Foster profile not found.")

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(profile, key, value)

        await self._repo._session.flush()
        res = await self._repo.get_profile_by_id(profile_id)
        if res is None:
            raise NotFoundError("Foster profile not found after update.")
        return res

    async def get_profile(self, profile_id: uuid.UUID) -> FosterProfile:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Foster profile not found.")
        return profile

    async def list_profiles(self, status: FosterStatus | None = None) -> Sequence[FosterProfile]:
        return await self._repo.list_profiles(status)

    async def place_dog(self, foster_id: uuid.UUID, payload: FosterPlacementCreate) -> FosterPlacement:
        foster = await self._repo.get_profile_by_id(foster_id)
        if foster is None:
            raise NotFoundError("Foster profile not found.")

        if foster.status != FosterStatus.APPROVED:
            raise ConflictError("Foster profile must be approved to place dogs.")

        if not foster.is_available or foster.active_count >= foster.max_capacity:
            raise ConflictError("Foster home has reached maximum capacity or is unavailable.")

        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        # Check if already placed or adopted
        if dog.status == DogStatus.ADOPTED:
            raise ConflictError("Cannot place an adopted dog into foster care.")

        existing_placement = await self._repo.get_active_placement_for_dog(payload.dog_id)
        if existing_placement is not None:
            raise ConflictError("Dog is already placed in foster care.")

        placement = FosterPlacement(
            foster_id=foster_id,
            dog_id=payload.dog_id,
            placed_at=datetime.now(UTC),
            is_active=True,
            notes=payload.notes,
        )
        await self._repo.create_placement(placement)

        # Update foster counts
        foster.active_count += 1
        if foster.active_count >= foster.max_capacity:
            foster.is_available = False

        # Update dog status
        dog.status = DogStatus.FOSTERED

        return placement

    async def return_dog(self, placement_id: uuid.UUID, *, notes: str | None = None) -> FosterPlacement:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")

        if not placement.is_active:
            raise ConflictError("Placement is already inactive.")

        now = datetime.now(UTC)
        placement.returned_at = now
        placement.is_active = False
        if notes:
            placement.notes = notes

        # Update foster counts
        foster = await self._repo.get_profile_by_id(placement.foster_id)
        if foster is not None:
            foster.active_count = max(0, foster.active_count - 1)
            if foster.active_count < foster.max_capacity:
                foster.is_available = True

        # Update dog status back to shelter
        dog = await self._dog_repo.get_by_id(placement.dog_id)
        if dog is not None:
            dog.status = DogStatus.SHELTER

        return placement
