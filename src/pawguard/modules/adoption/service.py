"""AdoptionService: owns all adoption vetting and exclusivity logic (RULE-003)."""

import uuid
from datetime import UTC, datetime

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import (
    AdoptionApplicationCreate,
    AdoptionApplicationResponse,
    AdoptionApplicationUpdate,
)
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.services.audit_service import AuditService


class AdoptionService:
    def __init__(
        self,
        repository: AdoptionRepository,
        dog_repo: DogRepository,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._audit = audit_service

    async def apply_for_adoption(
        self,
        adopter_id: uuid.UUID,
        payload: AdoptionApplicationCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AdoptionApplication:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        if not dog.is_adoptable:
            raise ConflictError("This dog is not currently cleared for adoption.")

        existing_approved = await self._repo.get_approved_application_for_dog(payload.dog_id)
        if existing_approved is not None:
            raise ConflictError(
                "This dog is already under an approved adoption application process."
            )

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

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADOPTION_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"adoption_id": str(res.id), "dog_id": str(payload.dog_id)},
            )

        return res

    async def update_application(
        self,
        app_id: uuid.UUID,
        payload: AdoptionApplicationUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AdoptionApplication:
        app = await self._repo.get_by_id(app_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")

        update_data = payload.model_dump(exclude_unset=True)

        if "status" in update_data:
            new_status = update_data["status"]

            if new_status in (AdoptionStatus.APPROVED, AdoptionStatus.COMPLETED):
                existing_approved = await self._repo.get_approved_application_for_dog(app.dog_id)
                if existing_approved is not None and existing_approved.id != app_id:
                    raise ConflictError(
                        "Another application has already been approved for this dog."
                    )

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

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADOPTION_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"adoption_id": str(app_id), "changes": update_data},
            )

        return res

    async def update_application_status(
        self,
        app_id: uuid.UUID,
        status: AdoptionStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AdoptionApplication:
        app = await self._repo.get_by_id(app_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")

        old_status = app.status

        if status in (AdoptionStatus.APPROVED, AdoptionStatus.COMPLETED):
            existing_approved = await self._repo.get_approved_application_for_dog(app.dog_id)
            if existing_approved is not None and existing_approved.id != app_id:
                raise ConflictError("Another application has already been approved for this dog.")

            dog = await self._dog_repo.get_by_id(app.dog_id)
            if dog is not None:
                dog.is_adoptable = False
                if status == AdoptionStatus.COMPLETED:
                    dog.status = DogStatus.ADOPTED

        if status == AdoptionStatus.COMPLETED:
            app.completed_at = datetime.now(UTC)

        app.status = status
        await self._repo._session.flush()
        res = await self._repo.get_by_id(app_id)
        if res is None:
            raise NotFoundError("Adoption application not found after status update.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADOPTION_STATUS_CHANGED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "adoption_id": str(app_id),
                    "old_status": old_status.value,
                    "new_status": status.value,
                },
            )

        return res

    async def get_application(self, app_id: uuid.UUID) -> AdoptionApplication:
        app = await self._repo.get_by_id(app_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")
        return app

    async def list_applications_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        status: AdoptionStatus | None = None,
        dog_id: uuid.UUID | None = None,
        adopter_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[AdoptionApplicationResponse]:
        results, total = await self._repo.list_paginated(
            page=page,
            sort=sort,
            search_term=search_term,
            status=status,
            dog_id=dog_id,
            adopter_id=adopter_id,
        )
        return PaginatedResponse(
            data=[AdoptionApplicationResponse.model_validate(a) for a in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def soft_delete_application(
        self,
        app_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        app = await self._repo.get_by_id(app_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")
        app.deleted_at = datetime.now(UTC)

        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADOPTION_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"adoption_id": str(app_id)},
            )

    async def bulk_update_status(
        self,
        ids: list[uuid.UUID],
        status: AdoptionStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        updated = await self._repo.bulk_update_status(ids, status)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.BULK_ADOPTION_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "adoption_ids": [str(i) for i in ids],
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
        for app_id in ids:
            app = await self._repo.get_by_id(app_id)
            if app is not None:
                app.deleted_at = datetime.now(UTC)
                count += 1

        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.BULK_ADOPTION_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"adoption_ids": [str(i) for i in ids], "count": count},
            )

        return count
