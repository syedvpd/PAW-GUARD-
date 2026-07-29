"""ShelterService: owns all shelter facilities, kennel allocations, sanitation tracking, and inter-facility transfers (RULE-003)."""

import uuid
from datetime import UTC, datetime
from typing import Sequence

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.shelter.models import (
    DailyCareLog,
    FacilityTransfer,
    Kennel,
    KennelSanitationState,
    ShelterFacility,
    ShelterSection,
    TransferStatus,
)
from pawguard.modules.shelter.repository import ShelterRepository
from pawguard.modules.shelter.schemas import (
    DailyCareLogCreate,
    FacilityTransferCreate,
    KennelCreate,
    ShelterFacilityCreate,
    ShelterSectionCreate,
)


class ShelterService:
    def __init__(self, repository: ShelterRepository, dog_repo: DogRepository) -> None:
        self._repo = repository
        self._dog_repo = dog_repo

    async def create_facility(self, payload: ShelterFacilityCreate) -> ShelterFacility:
        facility = ShelterFacility(
            name=payload.name,
            address=payload.address,
            phone=payload.phone,
            total_capacity=payload.total_capacity,
        )
        return await self._repo.create_facility(facility)

    async def create_section(self, facility_id: uuid.UUID, payload: ShelterSectionCreate) -> ShelterSection:
        facility = await self._repo.get_facility(facility_id)
        if facility is None:
            raise NotFoundError("Shelter facility not found.")

        section = ShelterSection(
            facility_id=facility_id,
            name=payload.name,
            capacity=payload.capacity,
        )
        return await self._repo.create_section(section)

    async def create_kennel(self, section_id: uuid.UUID, payload: KennelCreate) -> Kennel:
        section = await self._repo.get_section(section_id)
        if section is None:
            raise NotFoundError("Shelter section not found.")

        # Business Rule check: ensure adding this kennel doesn't exceed section capacity cap
        existing = await self._repo.list_kennels_by_section(section_id)
        if len(existing) >= section.capacity:
            raise ConflictError(f"Cannot add kennel. Section capacity limit ({section.capacity}) reached.")

        kennel = Kennel(
            section_id=section_id,
            identifier=payload.identifier,
            capacity=payload.capacity,
            sanitation_state=KennelSanitationState.CLEAN,
        )
        return await self._repo.create_kennel(kennel)

    async def assign_dog_to_kennel(self, dog_id: uuid.UUID, kennel_id: uuid.UUID) -> bool:
        dog = await self._dog_repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        kennel = await self._repo.get_kennel(kennel_id)
        if kennel is None:
            raise NotFoundError("Kennel not found.")

        # Business Validation: check sanitation state & availability
        if kennel.sanitation_state in (KennelSanitationState.NEEDS_CLEANING, KennelSanitationState.OUT_OF_SERVICE):
            raise ConflictError(f"Cannot assign dog. Kennel is currently {kennel.sanitation_state}.")

        section = await self._repo.get_section(kennel.section_id)
        if section is None:
            raise NotFoundError("Associated shelter section not found.")

        dog.shelter_facility_id = section.facility_id
        dog.kennel_id = kennel.id
        dog.status = DogStatus.SHELTER

        await self._dog_repo._session.flush()
        return True

    async def update_kennel_sanitation(self, kennel_id: uuid.UUID, status: KennelSanitationState) -> Kennel:
        kennel = await self._repo.get_kennel(kennel_id)
        if kennel is None:
            raise NotFoundError("Kennel not found.")

        kennel.sanitation_state = status
        await self._repo._session.flush()
        return kennel

    async def request_transfer(self, user_id: uuid.UUID, payload: FacilityTransferCreate) -> FacilityTransfer:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        from_fac = await self._repo.get_facility(payload.from_facility_id)
        to_fac = await self._repo.get_facility(payload.to_facility_id)
        if from_fac is None or to_fac is None:
            raise NotFoundError("Origin or destination facility not found.")

        transfer = FacilityTransfer(
            dog_id=payload.dog_id,
            from_facility_id=payload.from_facility_id,
            to_facility_id=payload.to_facility_id,
            transferred_by=user_id,
            status=TransferStatus.PENDING,
            notes=payload.notes,
        )
        return await self._repo.create_transfer(transfer)

    async def confirm_transfer(self, transfer_id: uuid.UUID) -> FacilityTransfer:
        transfer = await self._repo.get_transfer(transfer_id)
        if transfer is None:
            raise NotFoundError("Facility transfer request not found.")

        if transfer.status != TransferStatus.PENDING:
            raise ConflictError("Transfer request has already been processed.")

        dog = await self._dog_repo.get_by_id(transfer.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        # Update dog profile facility location
        dog.shelter_facility_id = transfer.to_facility_id
        dog.kennel_id = None  # require re-assignment to kennel at destination

        transfer.status = TransferStatus.COMPLETED
        await self._repo._session.flush()
        return transfer

    async def submit_daily_care_log(self, user_id: uuid.UUID, payload: DailyCareLogCreate) -> DailyCareLog:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        care_log = DailyCareLog(
            dog_id=payload.dog_id,
            logged_by=user_id,
            feed_time=datetime.now(UTC),
            dietary_requirements=payload.dietary_requirements,
            exercise_hours=payload.exercise_hours,
            behavioral_enrichment=payload.behavioral_enrichment,
        )
        return await self._repo.create_care_log(care_log)

    async def list_facilities(self) -> Sequence[ShelterFacility]:
        return await self._repo.list_facilities()

    async def list_sections(self, facility_id: uuid.UUID) -> Sequence[ShelterSection]:
        return await self._repo.list_sections_by_facility(facility_id)

    async def list_kennels(self, section_id: uuid.UUID) -> Sequence[Kennel]:
        return await self._repo.list_kennels_by_section(section_id)

    async def list_care_logs(self, dog_id: uuid.UUID) -> Sequence[DailyCareLog]:
        return await self._repo.list_care_logs_by_dog(dog_id)
