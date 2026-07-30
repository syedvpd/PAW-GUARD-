"""FosterService: owns foster applications, home availability, and placements (RULE-003)."""

import uuid
from datetime import UTC, datetime

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.foster.models import FosterPlacement, FosterProfile, FosterStatus
from pawguard.modules.foster.repository import FosterRepository
from pawguard.modules.foster.schemas import (
    FosterPlacementCreate,
    FosterProfileCreate,
    FosterProfileResponse,
    FosterProfileUpdate,
)
from pawguard.services.audit_service import AuditService


class FosterService:
    def __init__(
        self,
        repository: FosterRepository,
        dog_repo: DogRepository,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._audit = audit_service

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
        for key, value in update_data.items():
            setattr(profile, key, value)

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
        await self._repo.create_placement(placement)

        foster.active_count += 1
        if foster.active_count >= foster.max_capacity:
            foster.is_available = False

        dog.status = DogStatus.FOSTERED
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_PLACEMENT_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "placement_id": str(placement.id),
                    "dog_id": str(payload.dog_id),
                    "foster_id": str(foster_id),
                },
            )

        return placement

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
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FOSTER_PLACEMENT_ENDED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"placement_id": str(placement_id), "dog_id": str(placement.dog_id)},
            )

        return placement

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
