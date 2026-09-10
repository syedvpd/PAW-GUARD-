"""ShelterService: owns shelter facilities, kennel allocations,
sanitation tracking, and inter-facility transfers (RULE-003).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pawguard.core.cache_decorator import invalidate_route_cache
from pawguard.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from pawguard.core.logging import get_logger
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType, User
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.inventory.models import MovementType
from pawguard.modules.inventory.schemas import InventoryConsumptionItem, InventoryMovementCreate
from pawguard.modules.inventory.service import InventoryService
from pawguard.modules.notifications.schemas import BroadcastCreate
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.shelter.models import (
    DailyCareLog,
    FacilityStatus,
    FacilityTransfer,
    FacilityType,
    Kennel,
    KennelCleaningLog,
    KennelSanitationState,
    SectionType,
    ShelterFacility,
    ShelterSection,
    ShelterVetRequest,
    ShelterVetRequestStatus,
    TransferStatus,
)
from pawguard.modules.shelter.repository import ShelterRepository
from pawguard.modules.shelter.schemas import (
    DailyCareLogCreate,
    FacilityTransferCreate,
    KennelCleaningLogCreate,
    KennelCleaningLogResponse,
    KennelCreate,
    KennelResponse,
    ShelterFacilityCreate,
    ShelterFacilityResponse,
    ShelterFacilityUpdate,
    ShelterSectionCreate,
    ShelterSectionResponse,
    ShelterVetCheckRequest,
)
from pawguard.services.audit_service import AuditService

logger = get_logger(__name__)

_VALID_SHELTER_VET_REQUEST_TRANSITIONS: dict[
    ShelterVetRequestStatus, frozenset[ShelterVetRequestStatus]
] = {
    ShelterVetRequestStatus.PENDING: frozenset(
        {ShelterVetRequestStatus.IN_PROGRESS, ShelterVetRequestStatus.CANCELLED}
    ),
    ShelterVetRequestStatus.IN_PROGRESS: frozenset(
        {
            ShelterVetRequestStatus.COMPLETED,
            ShelterVetRequestStatus.REJECTED,
            ShelterVetRequestStatus.CANCELLED,
        }
    ),
    ShelterVetRequestStatus.COMPLETED: frozenset(),
    ShelterVetRequestStatus.REJECTED: frozenset(),
    ShelterVetRequestStatus.CANCELLED: frozenset(),
}

# Sections requiring veterinary sign-off for kennel assignment (master-spec
# rule, PRR §3.6) — mirrors the Flutter app's clinicalSectionTypes.
CLINICAL_SECTION_TYPES = {SectionType.QUARANTINE, SectionType.ISOLATION, SectionType.SURGICAL}


class ShelterService:
    def __init__(
        self,
        repository: ShelterRepository,
        dog_repo: DogRepository,
        audit_service: AuditService | None = None,
        inventory_service: InventoryService | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._audit = audit_service
        self._inventory = inventory_service
        self._notification_svc = notification_service

    async def _actor_role_names(self, actor_id: uuid.UUID | None) -> set[str]:
        if actor_id is None:
            return set()
        stmt = select(User).options(selectinload(User.roles)).where(User.id == actor_id)
        actor = (await self._repo._session.execute(stmt)).scalar_one_or_none()
        if actor is None:
            return set()
        return {r.name for r in actor.roles}

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

    async def get_facility(self, facility_id: uuid.UUID) -> ShelterFacility:
        facility = await self._repo.get_facility(facility_id)
        if facility is None:
            raise NotFoundError("Shelter facility not found.")
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
            section_type=payload.section_type,
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
                f"Cannot add kennel. Section capacity limit ({section.capacity}) reached."
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
        emergency_override: bool = False,
        override_notes: str | None = None,
    ) -> bool:
        dog = await self._dog_repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")
        prior_kennel_id = dog.kennel_id

        # Row-lock the kennel (SELECT ... FOR UPDATE) before the capacity and
        # sanitation check-then-act: two concurrent assignments to the same
        # kennel would otherwise both pass the availability check and double-book.
        kennel = await self._repo.get_kennel_for_update(kennel_id)
        if kennel is None:
            raise NotFoundError("Kennel not found.")

        # Business Validation: check sanitation state & availability
        bad_states = (
            KennelSanitationState.NEEDS_CLEANING,
            KennelSanitationState.DISINFECTING,
            KennelSanitationState.OUT_OF_SERVICE,
        )
        if kennel.sanitation_state in bad_states:
            raise ConflictError(
                f"Cannot assign dog. Kennel is currently {kennel.sanitation_state}."
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

        # Over-capacity gate: once a section is at (or would exceed) its
        # capacity, no further assignment into it is allowed until a kennel
        # is freed or the section's capacity is raised.
        section_occupied = await self._repo.count_occupied_in_section(
            section.id, exclude_dog_id=dog.id
        )
        if section_occupied >= section.capacity:
            raise ConflictError(
                f"Section '{section.name}' is at full capacity "
                f"({section_occupied}/{section.capacity}). Assignment blocked until resolved."
            )

        # Master-spec rule: Quarantine/Isolation/Surgical assignment normally
        # requires a veterinarian. A Shelter Manager may force it through in
        # a genuine emergency via emergency_override — a documented exception
        # path (mandatory justification, flagged for vet review), not a
        # silent bypass of the sign-off requirement.
        used_override = False
        if section.section_type in CLINICAL_SECTION_TYPES:
            actor_roles = await self._actor_role_names(actor_id)
            is_privileged = bool(
                actor_roles & {"veterinarian", "super_admin", "rescue_centre_admin"}
            )
            if not is_privileged:
                if not emergency_override:
                    raise ForbiddenError("Veterinary sign-off required for this section type")
                used_override = True

        dog.shelter_facility_id = section.facility_id
        dog.kennel_id = kennel.id
        dog.status = DogStatus.SHELTER

        await self._dog_repo._session.flush()
        await invalidate_route_cache("dog")
        await invalidate_route_cache("dashboards")

        if section_occupied + 1 >= section.capacity:
            await self._notify_section_full(section, section_occupied + 1, actor_id)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.KENNEL_ASSIGNED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "dog_id": str(dog_id),
                    "kennel_id": str(kennel_id),
                    "emergency_override": used_override,
                },
                before_state={"kennel_id": str(prior_kennel_id) if prior_kennel_id else None},
                after_state={"kennel_id": str(kennel_id)},
            )
        if used_override:
            await self._notify_clinical_override(dog, section, kennel, override_notes, actor_id)
        return True

    async def _notify_clinical_override(
        self,
        dog: DogProfile,
        section: ShelterSection,
        kennel: Kennel,
        override_notes: str | None,
        actor_id: uuid.UUID | None,
    ) -> None:
        if self._notification_svc is None:
            return
        try:
            await self._notification_svc.broadcast(
                payload=BroadcastCreate(
                    title=f"Emergency clinical kennel assignment: {section.name}",
                    body=(
                        f"A Shelter Manager assigned dog {dog.name} to kennel {kennel.identifier} "
                        f"in {section.name} ({section.section_type.value}) without veterinary sign-off — "
                        f"no vet immediately available. Justification: {override_notes}. "
                        "Please review within 24h."
                    ),
                    notification_type="shelter_clinical_override",
                    action_url=f"/dogs/{dog.id}",
                    target_roles=["veterinarian"],
                ),
                user_ids=[],
                actor_id=actor_id,
            )
        except Exception:  # pragma: no cover - alerting must never break the assignment
            logger.warning(
                "Failed to send clinical-override alert for dog %s", dog.id, exc_info=True
            )

    async def _notify_section_full(
        self,
        section: ShelterSection,
        occupied: int,
        actor_id: uuid.UUID | None,
    ) -> None:
        """Fires the instant a section hits 100% occupancy (RULE)."""
        if self._notification_svc is None:
            return
        try:
            await self._notification_svc.broadcast(
                payload=BroadcastCreate(
                    title=f"Section at capacity: {section.name}",
                    body=(
                        f"Section '{section.name}' has reached full capacity "
                        f"({occupied}/{section.capacity}). Further assignments are blocked "
                        "until a kennel is freed or capacity is increased."
                    ),
                    notification_type="shelter_section_full",
                    action_url=f"/shelter/kennel-grid?sectionId={section.id}",
                    target_roles=["rescue_centre_admin"],
                ),
                user_ids=[],
                actor_id=actor_id,
            )
        except Exception:  # pragma: no cover - alerting must never break the assignment
            logger.warning(
                "Failed to send section-full alert for section %s", section.id, exc_info=True
            )

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
        prior_status = kennel.sanitation_state

        kennel.sanitation_state = status
        await self._repo._session.flush()
        await self._repo._session.refresh(kennel, attribute_names=["updated_at"])
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
                before_state={"sanitation_state": prior_status.value},
                after_state={"sanitation_state": status.value},
            )
        return kennel

    async def log_kennel_cleaning(
        self,
        kennel_id: uuid.UUID,
        cleaned_by_id: uuid.UUID,
        payload: KennelCleaningLogCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> KennelCleaningLog:
        """Records a cleaning/disinfection rotation for a kennel (PRR 3.6).

        Creates a KennelCleaningLog row and, as its side effect, returns the
        kennel to CLEAN so it is immediately assignable again. The kennel row
        is locked for the duration of the transaction.
        """
        kennel = await self._repo.get_kennel_for_update(kennel_id)
        if kennel is None:
            raise NotFoundError("Kennel not found.")
        prior_status = kennel.sanitation_state

        log = KennelCleaningLog(
            kennel_id=kennel_id,
            cleaned_by=cleaned_by_id,
            cleaned_at=datetime.now(UTC),
            sanitation_state_after=KennelSanitationState.CLEAN,
            cleaning_method=payload.method,
            notes=payload.notes,
        )
        log = await self._repo.create_cleaning_log(log)

        kennel.sanitation_state = KennelSanitationState.CLEAN
        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.KENNEL_SANITATION_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "kennel_id": str(kennel_id),
                    "new_status": KennelSanitationState.CLEAN.value,
                    "cleaning_log_id": str(log.id),
                },
                before_state={"sanitation_state": prior_status.value},
                after_state={"sanitation_state": KennelSanitationState.CLEAN.value},
            )
        return log

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

        if payload.destination_kennel_id is not None:
            # Row-lock the destination kennel for the same reason kennel
            # assignment does: two transfers requested concurrently for the
            # same kennel must not both pass the availability check.
            kennel = await self._repo.get_kennel_for_update(payload.destination_kennel_id)
            if kennel is None:
                raise NotFoundError("Destination kennel not found.")
            kennel_section = await self._repo.get_section(kennel.section_id)
            if kennel_section is None or kennel_section.facility_id != payload.to_facility_id:
                raise ConflictError(
                    "Destination kennel does not belong to the destination facility."
                )
            if kennel.sanitation_state != KennelSanitationState.CLEAN:
                raise ConflictError(f"Destination kennel {kennel.identifier} is not Clean.")
            occupancy = await self._dog_repo.count_by_kennel(kennel.id)
            if occupancy >= kennel.capacity:
                raise ConflictError(f"Destination kennel {kennel.identifier} is occupied.")
            already_reserved = await self._repo.get_active_transfer_for_kennel(kennel.id)
            if already_reserved is not None:
                raise ConflictError(
                    f"Destination kennel {kennel.identifier} is already reserved by another pending transfer."
                )

        transfer = FacilityTransfer(
            dog_id=payload.dog_id,
            from_facility_id=payload.from_facility_id,
            to_facility_id=payload.to_facility_id,
            transferred_by=user_id,
            status=TransferStatus.PENDING,
            notes=payload.notes,
            destination_kennel_id=payload.destination_kennel_id,
            origin_kennel_id=dog.kennel_id,
            vehicle_id=payload.vehicle_id,
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

        if transfer.status not in (TransferStatus.PENDING, TransferStatus.IN_TRANSIT):
            raise ConflictError("Transfer request has already been processed.")

        other_side = "receiver" if side == "sender" else "sender"
        if getattr(transfer, f"{side}_confirmed_at") is not None:
            raise ConflictError(f"The {side} facility has already confirmed this transfer.")
        other_confirmed_by = getattr(transfer, f"{other_side}_confirmed_by")
        same_actor = other_confirmed_by is not None and other_confirmed_by == actor_id
        if actor_id is not None and same_actor:
            raise ConflictError(
                "The same user cannot confirm both the sending and receiving side of a transfer."
            )

        if actor_id is not None:
            import inspect

            actor_stmt = select(User).options(selectinload(User.roles)).where(User.id == actor_id)
            exec_res = await self._repo._session.execute(actor_stmt)
            actor = getattr(exec_res, "scalar_one_or_none", lambda: None)()
            if inspect.isawaitable(actor):
                actor = await actor
            if isinstance(actor, User):
                role_names = {r.name for r in getattr(actor, "roles", []) if hasattr(r, "name")}
                is_admin_override = bool(role_names & {"super_admin", "rescue_centre_admin"})
                if not is_admin_override:
                    required_facility_id = (
                        transfer.from_facility_id if side == "sender" else transfer.to_facility_id
                    )
                    if (
                        actor.managed_facility_id is None
                        or actor.managed_facility_id != required_facility_id
                    ):
                        facility_label = "sending" if side == "sender" else "receiving"
                        raise ForbiddenError(
                            f"User is not authorized to confirm {side} for this transfer. "
                            f"Caller's managed facility ({actor.managed_facility_id}) does not match the {facility_label} facility ({required_facility_id})."
                        )

        if side == "receiver" and transfer.sender_confirmed_at is None:
            raise ConflictError(
                "The sending facility must confirm dispatch before the receiving facility can confirm receipt."
            )

        now = datetime.now(UTC)
        setattr(transfer, f"{side}_confirmed_at", now)
        setattr(transfer, f"{side}_confirmed_by", actor_id)
        if side == "sender":
            transfer.status = TransferStatus.IN_TRANSIT

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
            if transfer.destination_kennel_id is not None:
                # Re-validate the reservation at completion time: it may have
                # gone dirty or been taken out of service since it was requested.
                kennel = await self._repo.get_kennel_for_update(transfer.destination_kennel_id)
                if kennel is None or kennel.sanitation_state != KennelSanitationState.CLEAN:
                    raise ConflictError(
                        "Destination kennel is no longer Open + Clean; cannot complete transfer."
                    )
                occupancy = await self._dog_repo.count_by_kennel(kennel.id, exclude_dog_id=dog.id)
                if occupancy >= kennel.capacity:
                    raise ConflictError(
                        "Destination kennel is no longer available; cannot complete transfer."
                    )
                dog.kennel_id = kennel.id
            else:
                dog.kennel_id = None  # require re-assignment to kennel at destination
            dog.shelter_facility_id = transfer.to_facility_id
            transfer.status = TransferStatus.COMPLETED

        await self._repo._session.flush()
        await self._repo._session.refresh(transfer, attribute_names=["updated_at"])
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

    async def cancel_transfer(
        self,
        transfer_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FacilityTransfer:
        """Cancels a transfer at any point before Completed (RULE). The dog's
        placement is untouched by Requested/SenderConfirmed/InTransit, so
        cancelling simply leaves it at the origin kennel — no revert needed."""
        transfer = await self._repo.get_transfer(transfer_id)
        if transfer is None:
            raise NotFoundError("Facility transfer request not found.")
        if transfer.status in (TransferStatus.COMPLETED, TransferStatus.CANCELLED):
            raise ConflictError(
                f"Transfer request is already {transfer.status.value} and cannot be cancelled."
            )

        transfer.status = TransferStatus.CANCELLED
        transfer.cancel_reason = reason
        await self._repo._session.flush()
        await self._repo._session.refresh(transfer, attribute_names=["updated_at"])

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.TRANSFER_CANCELLED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"transfer_id": str(transfer_id), "reason": reason},
            )
        return transfer

    async def find_available_quarantine_kennel(self) -> Kennel | None:
        """First Open + Clean Quarantine kennel at any active facility."""
        return await self._repo.find_available_kennel_by_section_type(SectionType.QUARANTINE)

    async def suggest_quarantine_kennel(self) -> tuple[Kennel, ShelterSection] | None:
        """Suggests a Quarantine kennel for the intake screen to pre-fill.

        A suggestion only — the rescue ADMITTED flow no longer auto-assigns
        it (PRR: staff must confirm placement, not have it silently
        committed). Returns the kennel with its section so the caller can
        resolve facility_id without a second round trip.
        """
        kennel = await self.find_available_quarantine_kennel()
        if kennel is None:
            return None
        section = await self._repo.get_section(kennel.section_id)
        if section is None:
            return None
        return kennel, section

    async def get_transfer(self, transfer_id: uuid.UUID) -> FacilityTransfer:
        transfer = await self._repo.get_transfer(transfer_id)
        if transfer is None:
            raise NotFoundError("Facility transfer request not found.")
        return transfer

    async def list_transfers(self) -> Sequence[FacilityTransfer]:
        return await self._repo.list_transfers()

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
            page_params,
            sort,
            search_term=search_term,
            status=status,
            facility_type=FacilityType(facility_type)
            if isinstance(facility_type, str)
            else facility_type,
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
        section_type: SectionType | None = None,
        search_term: str | None = None,
    ) -> PaginatedResponse[ShelterSectionResponse]:
        sections, total = await self._repo.list_sections_paginated(
            page_params,
            sort,
            facility_id=facility_id,
            section_type=section_type,
            search_term=search_term,
        )
        return PaginatedResponse(
            data=list(sections),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def list_cleaning_logs_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        kennel_id: uuid.UUID,
    ) -> PaginatedResponse[KennelCleaningLogResponse]:
        logs, total = await self._repo.list_cleaning_logs_paginated(
            page_params,
            sort,
            kennel_id=kennel_id,
        )
        return PaginatedResponse(
            data=list(logs),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def list_kennels_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        section_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[KennelResponse]:
        kennels, total = await self._repo.list_kennels_paginated(
            page_params,
            sort,
            section_id=section_id,
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

    async def update_facility(
        self,
        facility_id: uuid.UUID,
        payload: ShelterFacilityUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ShelterFacility:
        facility = await self._repo.get_facility(facility_id)
        if facility is None:
            raise NotFoundError("Shelter facility not found.")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(facility, field, value)
        await self._repo._session.flush()
        await self._repo._session.refresh(facility)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SHELTER_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"facility_id": str(facility_id)},
            )
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

    # --- Shelter Vet Check Request Workflow ---

    async def request_vet_check(
        self,
        dog_id: uuid.UUID,
        payload: "ShelterVetCheckRequest",
        *,
        actor_id: uuid.UUID,
        actor_roles: set[str],
        ip_address: str | None = None,
    ) -> ShelterVetRequest:
        """Create a persistent veterinary examination request for a shelter dog.

        Authorization (enforced here per RULE-003):
        - shelter_manager: scoped to their managed_facility_id
        - rescue_centre_admin: scoped to their facility
        - super_admin / system:admin: unrestricted
        """
        from pawguard.core.exceptions import ConflictError

        # 1. Load the dog and verify it exists
        dog = await self._dog_repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        # 2. Facility-scoped access control for shelter_manager and rescue_centre_admin
        if "super_admin" not in actor_roles and "system:admin" not in actor_roles:
            if dog.shelter_facility_id is None:
                raise ForbiddenError("This dog is not currently assigned to a shelter facility.")

            # For shelter_manager: verify the user manages this facility
            if "shelter_manager" in actor_roles or "rescue_centre_admin" in actor_roles:
                user = await self._get_user_with_roles(actor_id)
                if user is None or user.managed_facility_id != dog.shelter_facility_id:
                    raise ForbiddenError(
                        "You do not have access to request a vet check for a dog "
                        "at a different shelter facility."
                    )
            else:
                raise ForbiddenError(
                    "You do not have permission to request a vet check for this dog."
                )

        # 3. Validate the veterinarian exists and is active
        vet_user = await self._get_user_with_roles(payload.vet_id)
        if vet_user is None or not vet_user.is_active:
            raise NotFoundError("The selected veterinarian does not exist or is inactive.")

        # Check the vet actually has the veterinarian role
        vet_role_names = {r.name for r in vet_user.roles} if vet_user.roles else set()
        if "veterinarian" not in vet_role_names:
            raise NotFoundError("The selected user is not a registered veterinarian.")

        # 4. Idempotency: reject if an active request already exists for this dog
        existing = await self._repo.find_active_vet_request_for_dog(dog_id)
        if existing is not None:
            raise ConflictError(
                "An active veterinary request already exists for this dog. "
                "Please wait for the current request to be completed or cancelled."
            )

        # 5. Persist the request
        request = ShelterVetRequest(
            dog_id=dog_id,
            shelter_facility_id=dog.shelter_facility_id,
            requested_by_id=actor_id,
            vet_id=payload.vet_id,
            reason=payload.reason,
            notes=payload.notes,
            urgency=payload.urgency,
            status=ShelterVetRequestStatus.PENDING,
        )
        request = await self._repo.create_vet_request(request)

        # 6. Notification (best-effort, after successful persistence)
        try:
            await self._notify_vet_check_requested(
                request=request,
                dog=dog,
                actor_id=actor_id,
                vet_user=vet_user,
            )
        except Exception as exc:
            logger.warning("shelter_vet_check_notification_failed", error=str(exc))

        # 7. Audit log
        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.SHELTER_VET_CHECK_REQUESTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "request_id": str(request.id),
                    "dog_id": str(dog_id),
                    "vet_id": str(payload.vet_id),
                    "urgency": payload.urgency,
                    "reason": payload.reason,
                },
            )

        return request

    async def list_vet_requests_for_vet(
        self,
        vet_id: uuid.UUID,
        *,
        status: ShelterVetRequestStatus | None = None,
    ) -> list[dict[str, Any]]:
        """List vet requests assigned to a veterinarian with enriched data.

        Returns a list of dicts containing dog name, facility name, requester name, etc.
        """
        requests = await self._repo.list_vet_requests_for_vet(vet_id, status=status)
        return await self._enrich_vet_requests(requests)

    async def list_vet_requests_for_facility(
        self,
        facility_id: uuid.UUID,
        *,
        status: ShelterVetRequestStatus | None = None,
    ) -> list[dict[str, Any]]:
        """List all vet requests for a facility with enriched data."""
        requests = await self._repo.list_vet_requests_for_facility(facility_id, status=status)
        return await self._enrich_vet_requests(requests)

    async def update_vet_request_status(
        self,
        request_id: uuid.UUID,
        new_status: ShelterVetRequestStatus,
        *,
        actor_id: uuid.UUID | None = None,
        actor_roles: set[str] | None = None,
        ip_address: str | None = None,
    ) -> ShelterVetRequest:
        """Update the status of a shelter vet request.

        Authorization (enforced here per RULE-003):
        - veterinarian: scoped to requests assigned to them (clinical actions)
        - shelter_manager / rescue_centre_admin: scoped to their managed facility (cancel only)
        - super_admin / system:admin: unrestricted
        """
        request = await self._repo.get_vet_request(request_id)
        if request is None:
            raise NotFoundError("Shelter vet request not found.")

        roles = set(actor_roles or set())
        if not roles:
            raise ForbiddenError("You do not have permission to update the status of this request.")

        if "super_admin" in roles or "system:admin" in roles:
            pass
        elif "veterinarian" in roles:
            if actor_id is None or request.vet_id != actor_id:
                raise ForbiddenError("You can only update requests assigned to you.")
        elif "shelter_manager" in roles or "rescue_centre_admin" in roles:
            if actor_id is None:
                raise ForbiddenError(
                    "You do not have permission to update the status of this request."
                )
            actor = await self._get_user_with_roles(actor_id)
            if actor is None or actor.managed_facility_id != request.shelter_facility_id:
                raise ForbiddenError("You can only update requests for your shelter facility.")
            if new_status != request.status and new_status != ShelterVetRequestStatus.CANCELLED:
                raise ForbiddenError("Shelter staff may only cancel requests.")
        else:
            raise ForbiddenError("You do not have permission to update the status of this request.")

        if new_status != request.status:
            allowed = _VALID_SHELTER_VET_REQUEST_TRANSITIONS.get(request.status, frozenset())
            if new_status not in allowed:
                raise ValidationFailedError(
                    f"Cannot transition shelter vet request from {request.status} to {new_status}."
                )

        updated = await self._repo.update_vet_request_status(request_id, new_status)
        if updated is None:
            raise NotFoundError("Shelter vet request not found.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.SHELTER_VET_CHECK_REQUESTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "request_id": str(request_id),
                    "new_status": str(new_status),
                    "action": "status_update",
                },
            )

        return updated

    async def _enrich_vet_requests(
        self, requests: Sequence[ShelterVetRequest]
    ) -> list[dict[str, Any]]:
        """Enrich raw ShelterVetRequest records with dog, facility, and user names."""
        enriched: list[dict[str, Any]] = []
        for req in requests:
            dog = await self._dog_repo.get_by_id(req.dog_id)
            facility = await self._repo.get_facility(req.shelter_facility_id)
            vet_user = await self._get_user_with_roles(req.vet_id)
            requester_user = await self._get_user_with_roles(req.requested_by_id)

            enriched.append(
                {
                    "id": req.id,
                    "dog_id": req.dog_id,
                    "dog_name": dog.name if dog else "Unknown",
                    "shelter_facility_id": req.shelter_facility_id,
                    "shelter_facility_name": facility.name if facility else "Unknown",
                    "vet_id": req.vet_id,
                    "vet_name": vet_user.full_name if vet_user else "Unknown",
                    "requested_by_id": req.requested_by_id,
                    "requester_name": requester_user.full_name if requester_user else "Unknown",
                    "reason": req.reason,
                    "notes": req.notes,
                    "urgency": req.urgency,
                    "status": req.status,
                    "created_at": req.created_at,
                    "updated_at": req.updated_at,
                }
            )
        return enriched

    async def _get_user_with_roles(self, user_id: uuid.UUID) -> User | None:
        from sqlalchemy.orm import selectinload as _sel

        stmt = select(User).options(_sel(User.roles)).where(User.id == user_id)
        return (await self._repo._session.execute(stmt)).scalar_one_or_none()

    async def _notify_vet_check_requested(
        self,
        *,
        request: ShelterVetRequest,
        dog: DogProfile,
        actor_id: uuid.UUID,
        vet_user: User,
    ) -> None:
        """Send governed notification to the assigned veterinarian."""
        from pawguard.modules.notifications.governance_service import (
            dispatch_governed_notification,
        )

        actor = await self._get_user_with_roles(actor_id)
        actor_name = actor.full_name if actor else "Shelter Staff"
        dog_name = dog.name if dog else "Unknown dog"

        title = "Medical Check Requested"
        body = (
            f"{actor_name} has requested a veterinary examination for {dog_name}. "
            f"Reason: {request.reason}. "
            f"Urgency: {request.urgency.upper()}."
        )

        await dispatch_governed_notification(
            self._repo._session,
            trigger_code="shelter_vet_check_requested",
            module_name="shelter",
            title=title,
            body=body,
            target_user_ids=[request.vet_id],
            action_url=f"/shelter/dogs/{request.dog_id}",
            requested_by=actor_id,
        )
