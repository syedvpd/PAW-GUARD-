"""DogService: owns all dog profile and lifecycle business behavior (RULE-003)."""

import random
import uuid
from datetime import UTC, datetime
from typing import Sequence

from pawguard.core.exceptions import NotFoundError
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import DogProfileCreate, DogProfileUpdate


class DogService:
    def __init__(self, repository: DogRepository) -> None:
        self._repo = repository

    async def register_dog(self, payload: DogProfileCreate) -> DogProfile:
        year_str = datetime.now(UTC).strftime("%Y")
        rand_suffix = "".join(random.choices("0123456789", k=4))
        registration_number = f"DOG-{year_str}-{rand_suffix}"

        dog = DogProfile(
            registration_number=registration_number,
            rescue_case_id=payload.rescue_case_id,
            microchip_id=payload.microchip_id,
            name=payload.name,
            breed=payload.breed,
            gender=payload.gender.lower(),
            is_spayed_neutered=payload.is_spayed_neutered,
            estimated_age=payload.estimated_age,
            weight=payload.weight,
            color=payload.color,
            temperament=payload.temperament,
            status=DogStatus.RESCUED,
            shelter_facility_id=payload.shelter_facility_id,
            kennel_id=payload.kennel_id,
            is_adoptable=payload.is_adoptable,
            is_quarantine_passed=payload.is_quarantine_passed,
        )
        return await self._repo.create(dog)

    async def get_dog(self, dog_id: uuid.UUID) -> DogProfile:
        dog = await self._repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")
        return dog

    async def update_dog(self, dog_id: uuid.UUID, payload: DogProfileUpdate) -> DogProfile:
        dog = await self._repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        # Update fields dynamically
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(dog, key, value)

        return dog

    async def list_dogs(
        self, status: DogStatus | None = None, is_adoptable: bool | None = None
    ) -> Sequence[DogProfile]:
        return await self._repo.list_all(status=status, is_adoptable=is_adoptable)
