"""FosterService: owns foster applications, home availability, and placements (RULE-003)."""

import uuid
from datetime import UTC, datetime

from pawguard.core.config import get_settings
from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.pdf_generation import generate_adoption_agreement
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
)
from pawguard.modules.storage.models import FileFolder, StoredFile
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService


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
        for key, value in update_data.items():
            setattr(profile, key, value)

        # Coordinator approval (after the home inspection audit) is what
        # actually unlocks self-service foster access - the "foster_family"
        # role is granted here, not at application time, so an unvetted
        # applicant can't self-escalate before being cleared.
        if profile.status == FosterStatus.APPROVED and not was_approved:
            role = await self._roles.get_by_name("foster_family")
            if role is not None:
                await self._user_roles.grant_role(profile.user_id, role.id)

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
        # Attach the already-loaded dog: the placement is built in Python and
        # only flushed (never SELECTed), so its `dog` relationship would
        # otherwise lazy-load - which crashes in Pydantic's synchronous
        # response validation (MissingGreenlet) and needs no extra query.
        await self._repo.create_placement(placement)

        foster.active_count += 1
        if foster.active_count >= foster.max_capacity:
            foster.is_available = False

        dog.status = DogStatus.FOSTERED

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

    async def get_placement(self, placement_id: uuid.UUID) -> FosterPlacement:
        placement = await self._repo.get_placement_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Foster placement not found.")
        return placement

    async def list_supply_dispatches(
        self, placement_id: uuid.UUID
    ) -> list[FosterSupplyDispatch]:
        await self.get_placement(placement_id)
        dispatches = await self._repo.get_supply_dispatches_for_placement(placement_id)
        return list(dispatches)

    async def get_progress_logs(
        self, placement_id: uuid.UUID
    ) -> list[FosterProgressLog]:
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

        dog = await self._dog_repo.get_by_id(placement.dog_id)
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

        now = datetime.now(UTC)
        app = AdoptionApplication(
            dog_id=placement.dog_id,
            adopter_id=foster.user_id,
            residential_status="foster",
            has_landlord_approval=True,
            # Prefilled as True since the foster is already approved by the org
            has_yard_fence=True,         # Prefilled as True
            household_members_count=1,
            existing_pets_medical_details="None",
            pet_care_experience="Approved PawGuard Foster Caregiver",
            status=AdoptionStatus.COMPLETED,
            completed_at=now,
        )
        await self._adoption_repo.create(app)
        await self._repo._session.flush()

        # Generate and save adoption agreement PDF (legal lease)
        storage = StorageService()
        try:
            adopter_name = foster.user.full_name if foster.user else "Foster Parent"
            settings = get_settings()
            pdf_bytes = generate_adoption_agreement(
                adopter_name=adopter_name,
                dog_name=dog.name if dog else "Dog",
                dog_registration_number=dog.registration_number if dog else "",
                dog_breed=dog.breed if dog else "",
                fee_amount=0.0,
                org_name=settings.org_name,
                org_address=settings.org_address,
            )
            object_key = storage.build_object_key(
                folder="documents", filename=f"agreement_{app.id}.pdf"
            )
            storage.put_object(
                object_key=object_key,
                content=pdf_bytes,
                content_type="application/pdf",
            )
            stored = StoredFile(
                object_key=object_key,
                original_filename=f"adoption_agreement_{app.id}.pdf",
                mime_type="application/pdf",
                file_size=len(pdf_bytes),
                folder=FileFolder.DOCUMENTS.value,
                is_uploaded=True,
                uploaded_at=now,
                entity_type="adoption_application",
                entity_id=app.id,
            )
            self._repo._session.add(stored)
            app.adoption_agreement_url = object_key
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to generate agreement for foster-to-adopt application "
                "%s: %s", app.id, exc, exc_info=True,
            )

        placement.returned_at = now
        placement.is_active = False
        foster.active_count = max(0, foster.active_count - 1)
        if foster.active_count < foster.max_capacity:
            foster.is_available = True

        dog.status = DogStatus.ADOPTED

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
