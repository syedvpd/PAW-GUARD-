"""FosterService: owns foster applications, home availability, and placements (RULE-003)."""

import uuid
from datetime import UTC, datetime

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.logging import get_logger
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.auth.repository import RoleRepository, UserRoleRepository
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.foster.models import (
    FosterPlacement,
    FosterPlacementStatus,
    FosterProfile,
    FosterProgressLog,
    FosterStatus,
    FosterSupplyDispatch,
)
from pawguard.modules.foster.repository import FosterRepository
from pawguard.modules.foster.schemas import (
    FosterPlacementCreate,
    FosterProfileCreate,
    FosterProfileResponse,
    FosterProfileUpdate,
    FosterProgressLogCreate,
    FosterSupplyDispatchCreate,
    FosterVetCheckRequest,
    FosterVetCheckResponse,
)
from pawguard.modules.medical.repository import MedicalRepository
from pawguard.services.audit_service import AuditService

logger = get_logger(__name__)


class FosterService:
    def __init__(
        self,
        repository: FosterRepository,
        dog_repo: DogRepository,
        adoption_repo: AdoptionRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._adoption_repo = adoption_repo or AdoptionRepository(repository._session)
        self._audit = audit_service
        self._roles = RoleRepository(repository._session)
        self._user_roles = UserRoleRepository(repository._session)

    async def _send_push(
        self,
        user_ids: list[uuid.UUID],
        title: str,
        body: str,
        action_url: str | None = None,
    ) -> None:
        """Best-effort push notification via the notification service."""
        try:
            from pawguard.modules.notifications.repository import NotificationRepository
            from pawguard.modules.notifications.service import NotificationService

            svc = NotificationService(repository=NotificationRepository(self._repo._session))
            await svc._send_push_to_users(user_ids, title, body, action_url)
        except Exception as exc:
            logger.warning("Failed to send foster push notification: %s", exc)

    async def apply_to_foster(
        self,
        user_id: uuid.UUID,
        payload: FosterProfileCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FosterProfile:
        existing = await self._repo.get_profile_by_user_id(user_id)
        if existing is not None:
            raise ConflictError("You have already applied or registered as a foster home.")

        profile = FosterProfile(
            user_id=user_id,
            preferences=payload.preferences,
            max_capacity=payload.max_capacity,
            notes=payload.notes,
            status=FosterStatus.APPLIED,
            is_available=True,
        )
        await self._repo.create_profile(profile)
        res = await self._repo.get_profile_by_id(profile.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created foster profile.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_APPLICATION_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"profile_id": str(res.id)},
            )
        return res

    async def update_profile(
        self,
        profile_id: uuid.UUID,
        payload: FosterProfileUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FosterProfile:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Foster profile not found.")

        update_data = payload.model_dump(exclude_unset=True)
        was_approved = profile.status == FosterStatus.APPROVED

        background_check_passed = (
            payload.background_check_passed
            if payload.background_check_passed is not None
            else profile.background_check_passed
        )
        references_checked = (
            payload.references_checked
            if payload.references_checked is not None
            else profile.references_checked
        )
        home_inspection_passed = (
            payload.home_inspection_passed
            if payload.home_inspection_passed is not None
            else profile.home_inspection_passed
        )
        if payload.status == FosterStatus.APPROVED and not was_approved:
            if profile.status != FosterStatus.APPLIED:
                raise ConflictError("Only an applied foster profile can be approved.")
            # Block approval only if a vetting check was explicitly rejected/failed
            if background_check_passed is False or references_checked is False:
                raise ValidationFailedError(
                    "Cannot approve foster profile with a failed background check or rejected references."
                )
            if home_inspection_passed is False:
                raise ValidationFailedError(
                    "Cannot approve foster profile with a failed home inspection."
                )

            # When coordinator approves, clear pending vetting and record audit timestamps
            if (
                profile.background_check_passed is not True
                and payload.background_check_passed is None
            ):
                profile.background_check_passed = True
            if profile.references_checked is not True and payload.references_checked is None:
                profile.references_checked = True
            if (
                profile.home_inspection_passed is not True
                and payload.home_inspection_passed is None
            ):
                profile.home_inspection_passed = True
            if profile.vetted_at is None and payload.vetted_at is None:
                profile.vetted_at = datetime.now(UTC)
            if profile.inspected_at is None and payload.inspected_at is None:
                profile.inspected_at = datetime.now(UTC)

        if payload.status == FosterStatus.REJECTED and profile.status != FosterStatus.APPLIED:
            raise ConflictError("Only an applied foster profile can be rejected.")
        if payload.status == FosterStatus.INACTIVE and profile.active_count > 0:
            raise ConflictError("A foster home with active placements cannot be marked inactive.")
        for key, value in update_data.items():
            setattr(profile, key, value)

        if (
            payload.background_check_passed is not None
            and payload.vetted_at is None
            and profile.vetted_at is None
        ):
            profile.vetted_at = datetime.now(UTC)
        if (
            payload.home_inspection_passed is not None
            and payload.inspected_at is None
            and profile.inspected_at is None
        ):
            profile.inspected_at = datetime.now(UTC)

        # Coordinator approval (after the home inspection audit) is what
        # actually unlocks self-service foster access - the "foster_family"
        # role is granted here, not at application time, so an unvetted
        # applicant can't self-escalate before being cleared.
        if profile.status == FosterStatus.APPROVED and not was_approved:
            role = await self._roles.get_by_name("foster_family")
            if role is not None:
                await self._user_roles.grant_role(profile.user_id, role.id)
            await self._send_push(
                [profile.user_id],
                "Foster Application Approved",
                "Congratulations! Your foster application has been approved. You can now foster dogs.",
                "/foster",
            )

        await self._repo._session.flush()
        res = await self._repo.get_profile_by_id(profile_id)
        if res is None:
            raise NotFoundError("Foster profile not found after update.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_APPLICATION_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"profile_id": str(profile_id)},
            )
        return res

    async def get_profile(self, profile_id: uuid.UUID) -> FosterProfile:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Foster profile not found.")
        return profile

    async def get_my_profile(self, user_id: uuid.UUID) -> FosterProfile:
        profile = await self._repo.get_profile_by_user_id(user_id)
        if profile is None:
            raise NotFoundError("Foster profile not found for this user.")
        return profile

    async def get_my_placements(self, user_id: uuid.UUID) -> list[FosterPlacement]:
        profile = await self._repo.get_profile_by_user_id(user_id)
        if profile is None:
            raise NotFoundError("Foster profile not found for this user.")
        placements = await self._repo.get_placements_by_foster_id(profile.id)
        return list(placements)

    async def get_placements_for_profile(self, profile_id: uuid.UUID) -> list[FosterPlacement]:
        """Coordinator/admin view of a specific foster's placements (dogs
        assigned to them). get_my_placements above is the volunteer's own
        self-service equivalent; there was no admin-facing counterpart, so
        the admin app had no way to load a foster's assigned dogs from the
        database - it only ever showed placements created earlier in the
        same in-memory session."""
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Foster profile not found.")
        placements = await self._repo.get_placements_by_foster_id(profile_id)
        return list(placements)

    async def soft_delete_profile(
        self,
        profile_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Foster profile not found.")
        await self._repo.soft_delete_profile(profile_id)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"profile_id": str(profile_id)},
            )

    async def list_profiles_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: FosterStatus | None = None,
        is_available: bool | None = None,
    ) -> PaginatedResponse[FosterProfileResponse]:
        results, total = await self._repo.paginate_profiles(
            page=page,
            sort=sort,
            search_term=search_term,
            status=status,
            is_available=is_available,
        )
        return PaginatedResponse(
            data=[FosterProfileResponse.model_validate(p) for p in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def place_dog(
        self,
        foster_id: uuid.UUID,
        payload: FosterPlacementCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FosterPlacement:
        # Lock allocation before checking capacity so two coordinators cannot
        # consume the final foster slot concurrently.
        foster = await self._repo.get_profile_by_id_for_update(foster_id)
        if foster is None:
            raise NotFoundError("Foster profile not found.")

        if foster.status != FosterStatus.APPROVED:
            raise ConflictError("Foster profile must be approved to place dogs.")

        if not foster.is_available or foster.active_count >= foster.max_capacity:
            raise ConflictError("Foster home has reached maximum capacity or is unavailable.")

        dog = await self._dog_repo.get_by_id_for_update(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        if dog.status == DogStatus.ADOPTED:
            raise ConflictError("Cannot place an adopted dog into foster care.")
        if dog.status == DogStatus.FOSTERED:
            raise ConflictError("Dog is already in an active or adoption-pending foster placement.")

        medical_repo = MedicalRepository(self._repo._session)
        clearance = await medical_repo.get_latest_approved_clearance(payload.dog_id)
        if clearance is None:
            raise ValidationFailedError(
                "Dog is not medically eligible for foster placement. Record an "
                "approved, non-expired medical clearance or veterinarian foster "
                "exception first."
            )

        existing_placement = await self._repo.get_active_placement_for_dog(payload.dog_id)
        if existing_placement is not None:
            raise ConflictError("Dog is already placed in foster care.")

        placement = FosterPlacement(
            foster_id=foster_id,
            dog_id=payload.dog_id,
            placed_at=datetime.now(UTC),
            is_active=True,
            status=FosterPlacementStatus.ACTIVE,
            notes=payload.notes,
        )
        # Attach the already-loaded dog: the placement is built in Python and
        # only flushed (never SELECTed), so its `dog` relationship would
        # otherwise lazy-load - which crashes in Pydantic's synchronous
        # response validation (MissingGreenlet) and needs no extra query.
        await self._repo.create_placement(placement)

        foster.active_count += 1
        if foster.active_count >= foster.max_capacity:
            foster.is_available = False

        dog.status = DogStatus.FOSTERED
        # A fostered dog cannot retain a physical kennel allocation.
        dog.kennel_id = None

        # Re-fetch so the response serializer sees a fully-loaded object: the
        # placement is built in Python and only flushed (never SELECTed), so
        # its `dog` relationship would otherwise lazy-load - which crashes in
        # Pydantic's synchronous response validation (MissingGreenlet) - and
        # the flush just expired the dog's `updated_at` (onupdate=func.now()).
        # get_placement_by_id joins the dog (lazy="joined"), loading every
        # column in one SELECT.
        await self._repo._session.flush()
        res = await self._repo.get_placement_by_id(placement.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created foster placement.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_PLACEMENT_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "placement_id": str(res.id),
                    "dog_id": str(payload.dog_id),
                    "foster_id": str(foster_id),
                },
            )

        try:
            from pawguard.modules.notifications.governance_service import (
                dispatch_governed_notification,
            )

            await dispatch_governed_notification(
                self._repo._session,
                trigger_code="foster_assigned",
                module_name="foster",
                title=f"New Foster Placement: {dog.name}",
                body=f"You have been assigned to foster {dog.name}. Please check the foster portal for details.",
                target_user_ids=[foster.user_id],
                action_url=f"/foster/placements/{res.id}",
            )
        except Exception as exc:
            logger.warning("failed_sending_foster_placement_push", error=str(exc))

        dog_name = dog.name if dog else "A dog"
        await self._send_push(
            [foster.user_id],
            f"{dog_name} placed in your care",
            f"{dog_name} has been placed in your foster care. Please prepare for their arrival.",
            f"/foster/placements/{res.id}",
        )

        return res

    async def return_dog(
        self,
        placement_id: uuid.UUID,
        *,
        notes: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FosterPlacement:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")

        if not placement.is_active:
            raise ConflictError("Placement is already inactive.")

        now = datetime.now(UTC)
        placement.returned_at = now
        placement.is_active = False
        placement.status = FosterPlacementStatus.RETURNED
        if notes:
            placement.notes = notes

        foster = await self._repo.get_profile_by_id(placement.foster_id)
        if foster is not None:
            foster.active_count = max(0, foster.active_count - 1)
            if foster.active_count < foster.max_capacity:
                foster.is_available = True

        dog = await self._dog_repo.get_by_id(placement.dog_id)
        if dog is not None:
            dog.status = DogStatus.SHELTER

        # Re-fetch so the serializer sees non-expired columns (dog.updated_at
        # is expired by the flush via onupdate=func.now()) and the dog
        # relationship is loaded (see place_dog's MissingGreenlet note).
        await self._repo._session.flush()
        res = await self._repo.get_placement_by_id(placement_id)
        if res is None:
            raise NotFoundError("Failed to fetch foster placement after return.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_PLACEMENT_ENDED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"placement_id": str(res.id), "dog_id": str(res.dog_id)},
            )

        if foster is not None:
            dog_name = dog.name if dog else "The dog"
            await self._send_push(
                [foster.user_id],
                f"{dog_name} returned from foster care",
                f"{dog_name} has been returned to the shelter. Thank you for your care.",
                "/foster",
            )

        return res

    async def log_daily_progress(
        self,
        placement_id: uuid.UUID,
        payload: FosterProgressLogCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FosterProgressLog:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")
        if not placement.is_active:
            raise ConflictError("Placement is not active.")

        log = FosterProgressLog(
            placement_id=placement_id,
            tracked_by_id=actor_id,
            weight_kg=payload.weight_kg,
            behavior_notes=payload.behavior_notes,
            feeding_notes=payload.feeding_notes,
            medication_notes=payload.medication_notes,
            exercise_minutes=payload.exercise_minutes,
            photo_urls=payload.photo_urls,
            mood_rating=payload.mood_rating,
            notes=payload.notes,
            logged_at=datetime.now(UTC),
        )
        await self._repo.create_progress_log(log)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_PLACEMENT_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "placement_id": str(placement_id),
                    "progress_log_id": str(log.id),
                },
            )
        return log

    async def log_supply_dispatch(
        self,
        placement_id: uuid.UUID,
        payload: FosterSupplyDispatchCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FosterSupplyDispatch:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")

        dispatch = FosterSupplyDispatch(
            placement_id=placement_id,
            dispatched_by_id=actor_id,
            item_type=payload.item_type,
            description=payload.description,
            quantity=payload.quantity,
            dispatched_at=datetime.now(UTC),
        )
        await self._repo.create_supply_dispatch(dispatch)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_SUPPLY_DISPATCHED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "placement_id": str(placement_id),
                    "dispatch_id": str(dispatch.id),
                    "item_type": dispatch.item_type.value,
                    "quantity": dispatch.quantity,
                },
            )
        return dispatch

    async def request_supplies(
        self,
        placement_id: uuid.UUID,
        payload: FosterSupplyDispatchCreate,
        *,
        actor_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> FosterSupplyDispatch:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")
        if not placement.is_active:
            raise ConflictError("Cannot request supplies for an inactive foster placement.")

        dispatch = FosterSupplyDispatch(
            placement_id=placement_id,
            dispatched_by_id=actor_id,
            item_type=payload.item_type,
            description=f"[REQUESTED] {payload.description or ''}".strip(),
            quantity=payload.quantity,
            dispatched_at=datetime.now(UTC),
        )
        await self._repo.create_supply_dispatch(dispatch)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_SUPPLY_DISPATCHED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "placement_id": str(placement_id),
                    "dispatch_id": str(dispatch.id),
                    "item_type": dispatch.item_type.value,
                    "quantity": dispatch.quantity,
                    "type": "request",
                },
            )
        return dispatch

    async def get_placement(self, placement_id: uuid.UUID) -> FosterPlacement:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")
        return placement

    async def list_supply_dispatches(self, placement_id: uuid.UUID) -> list[FosterSupplyDispatch]:
        await self.get_placement(placement_id)
        dispatches = await self._repo.get_supply_dispatches_for_placement(placement_id)
        return list(dispatches)

    async def get_progress_logs(self, placement_id: uuid.UUID) -> list[FosterProgressLog]:
        await self.get_placement(placement_id)
        logs = await self._repo.get_progress_logs_for_placement(placement_id)
        return list(logs)

    async def convert_to_adoption(
        self,
        placement_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AdoptionApplication:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")
        if not placement.is_active:
            raise ConflictError("Placement is not active.")

        foster = await self._repo.get_profile_by_id(placement.foster_id)
        if foster is None:
            raise NotFoundError("Foster profile not found.")

        # PRR 3.5 / 3.7 / 3.8: Check dog status and existing applications
        dog = await self._dog_repo.get_by_id_for_update(placement.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")
        if dog.status == DogStatus.ADOPTED:
            raise ConflictError("This dog has already been adopted.")

        existing_approved = await self._adoption_repo.get_approved_application_for_dog(
            placement.dog_id
        )
        if existing_approved is not None:
            raise ConflictError(
                "This dog already has an approved adoption application in progress."
            )

        medical_repo = MedicalRepository(self._repo._session)
        clearance = await medical_repo.get_latest_approved_clearance(placement.dog_id)
        clearance_id_str = str(clearance.id) if clearance else "foster_care_clearance"

        now = datetime.now(UTC)
        app = AdoptionApplication(
            dog_id=placement.dog_id,
            adopter_id=foster.user_id,
            residential_status="foster",
            has_landlord_approval=True,
            # Prefilled as True since the foster is already approved by the org
            has_yard_fence=True,
            household_members_count=1,
            existing_pets_medical_details="None",
            pet_care_experience="Approved PawGuard Foster Caregiver",
            # Foster-to-adopt pre-populates the application and initiates adoption review
            status=AdoptionStatus.SUBMITTED,
        )
        await self._adoption_repo.create(app)
        await self._repo._session.flush()

        placement.returned_at = now
        placement.is_active = False
        placement.status = FosterPlacementStatus.CONVERTED_TO_ADOPT
        placement.adoption_application_id = app.id
        foster.active_count = max(0, foster.active_count - 1)
        if foster.active_count < foster.max_capacity:
            foster.is_available = True

        # Custody remains with the foster family while the application is
        # reviewed. AdoptionService performs the final adopted transition and
        # agreement generation after approval/handover.
        dog.status = DogStatus.FOSTERED

        await self._repo._session.flush()

        res = await self._adoption_repo.get_by_id(app.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created adoption application.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADOPTION_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "adoption_id": str(res.id),
                    "dog_id": str(placement.dog_id),
                    "source": "foster-to-adopt",
                    "medical_clearance_id": clearance_id_str,
                },
            )
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_PLACEMENT_ENDED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "placement_id": str(placement_id),
                    "dog_id": str(placement.dog_id),
                    "adoption_id": str(res.id),
                },
            )

        return res

    async def request_vet_check(
        self,
        placement_id: uuid.UUID,
        payload: FosterVetCheckRequest,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FosterVetCheckResponse:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")
        if not placement.is_active:
            raise ConflictError("Cannot request vet check for an inactive foster placement.")

        foster = await self._repo.get_profile_by_id(placement.foster_id)
        dog = await self._dog_repo.get_by_id(placement.dog_id)
        dog_name = dog.name if dog else "Foster dog"

        now = datetime.now(UTC)
        tracking_user_id = actor_id or (foster.user_id if foster else None)
        if tracking_user_id:
            log = FosterProgressLog(
                placement_id=placement_id,
                tracked_by_id=tracking_user_id,
                behavior_notes=f"VET CHECK REQUESTED: [{payload.urgency.upper()}] {payload.reason or 'Routine inspection'} - {payload.notes or ''}".strip(),
                logged_at=now,
            )
            await self._repo.create_progress_log(log)

        try:
            from pawguard.modules.notifications.governance_service import (
                dispatch_governed_notification,
            )

            await dispatch_governed_notification(
                self._repo._session,
                trigger_code="foster_vet_check_requested",
                module_name="foster",
                title=f"Vet Check Requested: {dog_name}",
                body=f"Veterinary check requested for {dog_name} (Urgency: {payload.urgency.upper()}). Reason: {payload.reason or 'Health check'}",
                target_user_ids=[foster.user_id] if foster else [],
                action_url=f"/foster/placements/{placement_id}",
            )
        except Exception as exc:
            logger.warning("failed_sending_vet_check_push", error=str(exc))

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_VET_CHECK_REQUESTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "placement_id": str(placement_id),
                    "dog_id": str(placement.dog_id),
                    "urgency": payload.urgency,
                    "reason": payload.reason,
                },
            )

        return FosterVetCheckResponse(
            placement_id=placement_id,
            dog_id=placement.dog_id,
            foster_id=placement.foster_id,
            reason=payload.reason or "Routine health assessment",
            urgency=payload.urgency,
            status="requested",
            requested_at=now,
            message="Veterinary check request has been initiated and forwarded to the medical team.",
        )

    async def bulk_soft_delete(
        self,
        ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_soft_delete_profiles(ids)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"profile_ids": [str(i) for i in ids], "count": count},
            )
        return count
