"""DogService: owns all dog profile and lifecycle business behavior (RULE-003)."""

import secrets
import uuid
from datetime import UTC, datetime

from pawguard.core.exceptions import NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import DogProfileCreate, DogProfileResponse, DogProfileUpdate
from pawguard.services.audit_service import AuditService


class DogService:
    def __init__(
        self, repository: DogRepository, audit_service: AuditService | None = None
    ) -> None:
        self._repo = repository
        self._audit = audit_service

    async def register_dog(
        self,
        payload: DogProfileCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DogProfile:
        year_str = datetime.now(UTC).strftime("%Y")
        rand_suffix = "".join(secrets.choice("0123456789") for _ in range(4))
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
        dog = await self._repo.create(dog)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DOG_REGISTERED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"dog_id": str(dog.id), "registration_number": registration_number},
            )

        return dog

    async def get_dog(self, dog_id: uuid.UUID) -> DogProfile:
        dog = await self._repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")
        return dog

    async def update_dog(
        self,
        dog_id: uuid.UUID,
        payload: DogProfileUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DogProfile:
        dog = await self._repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(dog, key, value)

        await self._repo._session.flush()
        await self._repo._session.refresh(dog)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DOG_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"dog_id": str(dog_id), "changes": update_data},
            )

        return dog

    async def update_dog_status(
        self,
        dog_id: uuid.UUID,
        status: DogStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DogProfile:
        dog = await self.get_dog(dog_id)
        old_status = dog.status
        dog.status = status

        await self._repo._session.flush()
        await self._repo._session.refresh(dog)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DOG_STATUS_CHANGED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "dog_id": str(dog_id),
                    "old_status": old_status.value,
                    "new_status": status.value,
                },
            )

        return dog

    async def soft_delete_dog(
        self,
        dog_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        dog = await self.get_dog(dog_id)
        dog.deleted_at = datetime.now(UTC)

        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DOG_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"dog_id": str(dog_id), "registration_number": dog.registration_number},
            )

    async def list_dogs_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: DogStatus | None = None,
        is_adoptable: bool | None = None,
        breed: str | None = None,
        gender: str | None = None,
        temperament: str | None = None,
    ) -> PaginatedResponse[DogProfileResponse]:
        results, total = await self._repo.list_paginated(
            page=page,
            sort=sort,
            search_term=search_term,
            status=status,
            is_adoptable=is_adoptable,
            breed=breed,
            gender=gender,
            temperament=temperament,
        )
        return PaginatedResponse(
            data=[DogProfileResponse.model_validate(d) for d in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def bulk_update_status(
        self,
        ids: list[uuid.UUID],
        status: DogStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        updated = await self._repo.bulk_update_status(ids, status)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.BULK_DOG_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "dog_ids": [str(i) for i in ids],
                    "status": status.value,
                    "count": updated,
                },
            )

        return updated

    async def bulk_soft_delete(
        self,
        ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = 0
        for dog_id in ids:
            dog = await self._repo.get_by_id(dog_id)
            if dog is not None:
                dog.deleted_at = datetime.now(UTC)
                count += 1

        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.BULK_DOG_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"dog_ids": [str(i) for i in ids], "count": count},
            )

        return count
