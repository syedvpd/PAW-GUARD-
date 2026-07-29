"""AdoptionService: owns all adoption vetting and exclusivity logic (RULE-003)."""

import uuid
from datetime import UTC, datetime
from typing import Sequence

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import AdoptionApplicationCreate, AdoptionApplicationUpdate
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository


class AdoptionService:
    def __init__(self, repository: AdoptionRepository, dog_repo: DogRepository) -> None:
        self._repo = repository
        self._dog_repo = dog_repo

    async def apply_for_adoption(
        self, adopter_id: uuid.UUID, payload: AdoptionApplicationCreate
    ) -> AdoptionApplication:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        # Check if the dog is adoptable
        if not dog.is_adoptable:
            raise ConflictError("This dog is not currently cleared for adoption.")

        # Check Exclusivity Enforcement Engine:
        # If the dog already has an approved adoption application, reject new ones.
        existing_approved = await self._repo.get_approved_application_for_dog(payload.dog_id)
        if existing_approved is not None:
            raise ConflictError("This dog is already under an approved adoption application process.")

        app = AdoptionApplication(
            dog_id=payload.dog_id,
            adopter_id=adopter_id,
            residential_status=payload.residential_status,
            has_landlord_approval=payload.has_landlord_approval,
            has_yard_fence=payload.has_yard_fence,
            household_members_count=payload.household_members_count,
            existing_pets_medical_details=payload.existing_pets_medical_details,
            pet_care_experience=payload.pet_care_experience,
            status=AdoptionStatus.SUBMITTED,
        )
        await self._repo.create(app)
        res = await self._repo.get_by_id(app.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created adoption application.")
        return res

    async def update_application(
        self, app_id: uuid.UUID, payload: AdoptionApplicationUpdate
    ) -> AdoptionApplication:
        app = await self._repo.get_by_id(app_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")

        update_data = payload.model_dump(exclude_unset=True)

        if "status" in update_data:
            new_status = update_data["status"]

            # Exclusivity Enforcement Engine
            if new_status in (AdoptionStatus.APPROVED, AdoptionStatus.COMPLETED):
                existing_approved = await self._repo.get_approved_application_for_dog(app.dog_id)
                if existing_approved is not None and existing_approved.id != app_id:
                    raise ConflictError("Another application has already been approved for this dog.")

                # Lock the dog's adoptable status and update lifecycle status
                dog = await self._dog_repo.get_by_id(app.dog_id)
                if dog is not None:
                    dog.is_adoptable = False
                    if new_status == AdoptionStatus.COMPLETED:
                        dog.status = DogStatus.ADOPTED

            if new_status == AdoptionStatus.COMPLETED:
                app.completed_at = datetime.now(UTC)

        for key, value in update_data.items():
            setattr(app, key, value)

        await self._repo._session.flush()
        res = await self._repo.get_by_id(app_id)
        if res is None:
            raise NotFoundError("Adoption application not found after update.")
        return res

    async def get_application(self, app_id: uuid.UUID) -> AdoptionApplication:
        app = await self._repo.get_by_id(app_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")
        return app

    async def list_applications(
        self,
        dog_id: uuid.UUID | None = None,
        adopter_id: uuid.UUID | None = None,
        status: AdoptionStatus | None = None,
    ) -> Sequence[AdoptionApplication]:
        if dog_id is not None:
            return await self._repo.list_by_dog(dog_id)
        if adopter_id is not None:
            return await self._repo.list_by_adopter(adopter_id)
        return await self._repo.list_all(status)
