"""ShelterService: owns shelter facilities, kennel allocations,
sanitation tracking, and inter-facility transfers (RULE-003).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.inventory.models import MovementType
from pawguard.modules.inventory.schemas import InventoryConsumptionItem, InventoryMovementCreate
from pawguard.modules.inventory.service import InventoryService
from pawguard.modules.shelter.models import (
    DailyCareLog,
    FacilityStatus,
    FacilityTransfer,
    FacilityType,
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
    KennelResponse,
    ShelterFacilityCreate,
    ShelterFacilityResponse,
    ShelterSectionCreate,
    ShelterSectionResponse,
)
from pawguard.services.audit_service import AuditService


class ShelterService:
    def __init__(
        self,
        repository: ShelterRepository,
        dog_repo: DogRepository,
        audit_service: AuditService | None = None,
        inventory_service: InventoryService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._audit = audit_service
        self._inventory = inventory_service

    async def create_facility(
        self,
        payload: ShelterFacilityCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ShelterFacility:
        existing = await self._repo.get_facility_by_name(payload.name)
        if existing is not None:
            raise ConflictError(f"A shelter facility named '{payload.name}' already exists.")

        facility = ShelterFacility(
            name=payload.name,
            address=payload.address,
            phone=payload.phone,
            total_capacity=payload.total_capacity,
            facility_type=payload.facility_type,
        )
        facility = await self._repo.create_facility(facility)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SHELTER_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"facility_id": str(facility.id)},
            )
        return facility

    async def create_section(
        self,
        facility_id: uuid.UUID,
        payload: ShelterSectionCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ShelterSection:
        facility = await self._repo.get_facility(facility_id)
        if facility is None:
            raise NotFoundError("Shelter facility not found.")

        section = ShelterSection(
            facility_id=facility_id,
            name=payload.name,
            capacity=payload.capacity,
        )
        section = await self._repo.create_section(section)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SHELTER_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "facility_id": str(facility_id),
                    "section_id": str(section.id),
                },
            )
        return section

    async def create_kennel(
        self,
        section_id: uuid.UUID,
        payload: KennelCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Kennel:
        section = await self._repo.get_section(section_id)
        if section is None:
            raise NotFoundError("Shelter section not found.")

        # Business Rule check: ensure adding this kennel doesn't exceed section capacity cap
        existing = await self._repo.list_kennels_by_section(section_id)
        if len(existing) >= section.capacity:
            raise ConflictError(
                f"Cannot add kennel. Section capacity limit "
                f"({section.capacity}) reached."
            )

        kennel = Kennel(
            section_id=section_id,
            identifier=payload.identifier,
            capacity=payload.capacity,
            sanitation_state=KennelSanitationState.CLEAN,
        )
        kennel = await self._repo.create_kennel(kennel)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SHELTER_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "section_id": str(section_id),
                    "kennel_id": str(kennel.id),
                },
            )
        return kennel

    async def assign_dog_to_kennel(
        self,
        dog_id: uuid.UUID,
        kennel_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> bool:
        dog = await self._dog_repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        kennel = await self._repo.get_kennel(kennel_id)
        if kennel is None:
            raise NotFoundError("Kennel not found.")

        # Business Validation: check sanitation state & availability
        bad_states = (
            KennelSanitationState.NEEDS_CLEANING,
            KennelSanitationState.OUT_OF_SERVICE,
        )
        if kennel.sanitation_state in bad_states:
            raise ConflictError(
                f"Cannot assign dog. Kennel is currently "
                f"{kennel.sanitation_state}."
            )

        occupancy = await self._dog_repo.count_by_kennel(kennel.id, exclude_dog_id=dog.id)
        if occupancy >= kennel.capacity:
            raise ConflictError(
                f"Cannot assign dog. Kennel {kennel.identifier} is at capacity "
                f"({occupancy}/{kennel.capacity})."
            )

        section = await self._repo.get_section(kennel.section_id)
        if section is None:
            raise NotFoundError("Associated shelter section not found.")

        dog.shelter_facility_id = section.facility_id
        dog.kennel_id = kennel.id
        dog.status = DogStatus.SHELTER

        await self._dog_repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.KENNEL_ASSIGNED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "dog_id": str(dog_id),
                    "kennel_id": str(kennel_id),
                },
            )
        return True

    async def update_kennel_sanitation(
        self,
        kennel_id: uuid.UUID,
        status: KennelSanitationState,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Kennel:
        kennel = await self._repo.get_kennel(kennel_id)
        if kennel is None:
            raise NotFoundError("Kennel not found.")

        kennel.sanitation_state = status
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.KENNEL_SANITATION_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "kennel_id": str(kennel_id),
                    "new_status": status.value,
                },
            )
        return kennel

    async def request_transfer(
        self,
        user_id: uuid.UUID,
        payload: FacilityTransferCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FacilityTransfer:
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
        transfer = await self._repo.create_transfer(transfer)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.TRANSFER_REQUESTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "transfer_id": str(transfer.id),
                    "dog_id": str(payload.dog_id),
                },
            )
        return transfer

    async def _confirm_transfer_side(
        self,
        transfer_id: uuid.UUID,
        side: str,
        actor_id: uuid.UUID | None,
        ip_address: str | None,
    ) -> FacilityTransfer:
        """Records one side's (sender's or receiver's) confirmation.

        A transfer only completes once BOTH sides have confirmed (PRR 3.6);
        the requesting facility cannot unilaterally complete its own
        transfer, and the same actor cannot confirm both sides.
        """
        transfer = await self._repo.get_transfer(transfer_id)
        if transfer is None:
            raise NotFoundError("Facility transfer request not found.")

        if transfer.status != TransferStatus.PENDING:
            raise ConflictError("Transfer request has already been processed.")

        other_side = "receiver" if side == "sender" else "sender"
        if getattr(transfer, f"{side}_confirmed_at") is not None:
            raise ConflictError(f"The {side} facility has already confirmed this transfer.")
        other_confirmed_by = getattr(transfer, f"{other_side}_confirmed_by")
        same_actor = other_confirmed_by is not None and other_confirmed_by == actor_id
        if actor_id is not None and same_actor:
            raise ConflictError(
                "The same user cannot confirm both the sending and receiving side "
                "of a transfer."
            )

        now = datetime.now(UTC)
        setattr(transfer, f"{side}_confirmed_at", now)
        setattr(transfer, f"{side}_confirmed_by", actor_id)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.TRANSFER_CONFIRMED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"transfer_id": str(transfer_id), "side": side},
            )

        if transfer.sender_confirmed_at is not None and transfer.receiver_confirmed_at is not None:
            dog = await self._dog_repo.get_by_id(transfer.dog_id)
            if dog is None:
                raise NotFoundError("Dog profile not found.")
            dog.shelter_facility_id = transfer.to_facility_id
            dog.kennel_id = None  # require re-assignment to kennel at destination
            transfer.status = TransferStatus.COMPLETED

        await self._repo._session.flush()
        return transfer

    async def confirm_transfer_sender(
        self,
        transfer_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FacilityTransfer:
        return await self._confirm_transfer_side(transfer_id, "sender", actor_id, ip_address)

    async def confirm_transfer_receiver(
        self,
        transfer_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FacilityTransfer:
        return await self._confirm_transfer_side(transfer_id, "receiver", actor_id, ip_address)

    async def submit_daily_care_log(
        self,
        user_id: uuid.UUID,
        payload: DailyCareLogCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DailyCareLog:
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
        care_log = await self._repo.create_care_log(care_log)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.CARE_LOG_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "care_log_id": str(care_log.id),
                    "dog_id": str(payload.dog_id),
                },
            )
        await self._record_inventory_consumptions(
            user_id=user_id,
            consumptions=payload.inventory_consumptions,
            reference_type="daily_care_log",
            reference_id=care_log.id,
            actor_id=actor_id,
            ip_address=ip_address,
        )
        return care_log

    async def list_facilities(self) -> Sequence[ShelterFacility]:
        return await self._repo.list_facilities()

    async def list_sections(self, facility_id: uuid.UUID) -> Sequence[ShelterSection]:
        return await self._repo.list_sections_by_facility(facility_id)

    async def list_kennels(self, section_id: uuid.UUID) -> Sequence[Kennel]:
        return await self._repo.list_kennels_by_section(section_id)

    async def list_care_logs(self, dog_id: uuid.UUID) -> Sequence[DailyCareLog]:
        return await self._repo.list_care_logs_by_dog(dog_id)

    async def list_facilities_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: FacilityStatus | None = None,
        facility_type: str | None = None,
    ) -> PaginatedResponse[ShelterFacilityResponse]:
        facilities, total = await self._repo.list_facilities_paginated(
            page_params, sort, search_term=search_term, status=status,
            facility_type=FacilityType(facility_type) if facility_type else None,
        )
        return PaginatedResponse(
            data=list(facilities),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def list_sections_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        facility_id: uuid.UUID | None = None,
        search_term: str | None = None,
    ) -> PaginatedResponse[ShelterSectionResponse]:
        sections, total = await self._repo.list_sections_paginated(
            page_params, sort, facility_id=facility_id, search_term=search_term,
        )
        return PaginatedResponse(
            data=list(sections),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def list_kennels_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        section_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[KennelResponse]:
        kennels, total = await self._repo.list_kennels_paginated(
            page_params, sort, section_id=section_id,
        )
        return PaginatedResponse(
            data=list(kennels),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def soft_delete_facility(self, facility_id: uuid.UUID) -> None:
        deleted = await self._repo.soft_delete_facility(facility_id)
        if not deleted:
            raise NotFoundError("Shelter facility not found.")

    async def update_facility_status(
        self,
        facility_id: uuid.UUID,
        status: FacilityStatus,
    ) -> ShelterFacility:
        facility = await self._repo.get_facility(facility_id)
        if facility is None:
            raise NotFoundError("Shelter facility not found.")
        facility.status = status
        await self._repo._session.flush()
        await self._repo._session.refresh(facility)
        return facility

    async def bulk_delete_facilities(self, ids: list[uuid.UUID]) -> int:
        return await self._repo.bulk_delete_facilities(ids)

    async def bulk_update_facility_status(
        self,
        ids: list[uuid.UUID],
        status: FacilityStatus,
    ) -> int:
        return await self._repo.bulk_update_facility_status(ids, status)

    async def _record_inventory_consumptions(
        self,
        user_id: uuid.UUID,
        consumptions: list[InventoryConsumptionItem] | None,
        reference_type: str,
        reference_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        ip_address: str | None,
    ) -> None:
        if not self._inventory or not consumptions:
            return
        for item in consumptions:
            await self._inventory.record_movement(
                user_id=user_id,
                payload=InventoryMovementCreate(
                    item_id=item.item_id,
                    movement_type=MovementType.CHECK_OUT,
                    quantity=item.quantity,
                    notes=f"Consumed for {reference_type} {reference_id}",
                    reference_type=reference_type,
                    reference_id=reference_id,
                ),
                actor_id=actor_id,
                ip_address=ip_address,
            )
