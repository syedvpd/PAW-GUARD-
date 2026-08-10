"""AdoptionService: owns all adoption vetting and exclusivity logic (RULE-003)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from logging import getLogger

from pawguard.core.config import get_settings
from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.pdf_generation import generate_adoption_agreement
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import (
    AdoptionApplication,
    AdoptionFollowUp,
    AdoptionScore,
    AdoptionStatus,
    FollowUpStatus,
)
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import (
    AdoptionApplicationCreate,
    AdoptionApplicationResponse,
    AdoptionApplicationUpdate,
    AdoptionScoreCreate,
)
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.shelter.repository import ShelterRepository
from pawguard.modules.shelter.schemas import NearbyShelterResponse
from pawguard.modules.storage.models import FileFolder, StoredFile
from pawguard.redis.client import RedisClient
from pawguard.services.audit_service import AuditService
from pawguard.services.cache_service import CacheService
from pawguard.services.storage_service import StorageService

logger = getLogger(__name__)


# Post-adoption check-in milestones, in days after completion (PRR 3.7).
FOLLOW_UP_INTERVALS = (30, 90, 180)

# Explicit state machine for the 6-phase vetting pipeline (PRR 3.7):
# SUBMITTED -> SCREENING -> INTERVIEW -> HOME_CHECK -> APPROVED -> COMPLETED.
# REJECTED is reachable from any pre-completion state (an application can be
# rejected at document review, interview, or home inspection); nothing is
# reachable from a terminal state. The deprecated legacy VETTING member is a
# data-compatibility holdover and is deliberately absent from the graph.
VALID_STATUS_TRANSITIONS: dict[AdoptionStatus, set[AdoptionStatus]] = {
    AdoptionStatus.SUBMITTED: {AdoptionStatus.SCREENING, AdoptionStatus.REJECTED},
    AdoptionStatus.SCREENING: {AdoptionStatus.INTERVIEW, AdoptionStatus.REJECTED},
    AdoptionStatus.INTERVIEW: {AdoptionStatus.HOME_CHECK, AdoptionStatus.REJECTED},
    AdoptionStatus.HOME_CHECK: {AdoptionStatus.APPROVED, AdoptionStatus.REJECTED},
    AdoptionStatus.APPROVED: {AdoptionStatus.COMPLETED, AdoptionStatus.REJECTED},
    AdoptionStatus.COMPLETED: set(),
    AdoptionStatus.REJECTED: set(),
    AdoptionStatus.VETTING: set(),
}


class AdoptionService:
    def __init__(
        self,
        repository: AdoptionRepository,
        dog_repo: DogRepository,
        audit_service: AuditService | None = None,
        storage_service: StorageService | None = None,
        redis_client: RedisClient | None = None,
        shelter_repo: ShelterRepository | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._redis = redis_client
        self._audit = audit_service
        self._storage = storage_service
        self._shelter_repo = shelter_repo
        self._notification_svc = notification_service



    async def _notify_adopter(
        self,
        application: AdoptionApplication,
        *,
        title: str,
        body: str,
        notification_type: str,
        action_url: str | None = None,
    ) -> None:
        """Send the adopter an in-app notification and email about their application."""
        if self._notification_svc is None or application.adopter is None:
            return
        try:
            from pawguard.modules.notifications.schemas import NotificationSend
            await self._notification_svc.send_notification(
                payload=NotificationSend(
                    user_id=application.adopter_id,
                    title=title,
                    body=body,
                    notification_type=notification_type,
                    action_url=action_url,
                    send_email=True,
                ),
                user_email=application.adopter.email,
            )
        except Exception as exc:
            logger.warning(
                "Failed to notify adopter for application %s: %s",
                application.id,
                exc,
                exc_info=True,
            )


    async def _generate_agreement(self, application: AdoptionApplication) -> None:
        if self._storage is None:
            return
        try:
            adopter_name = (
                application.adopter.full_name
                if application.adopter
                else "Adopter"
            )
            dog = application.dog
            settings = get_settings()
            pdf_bytes = generate_adoption_agreement(
                adopter_name=adopter_name,
                dog_name=dog.name if dog else "Dog",
                dog_registration_number=dog.registration_number if dog else "",
                dog_breed=dog.breed if dog else "",
                fee_amount=float(application.fee_amount or Decimal("0.00")),
                org_name=settings.org_name,
                org_address=settings.org_address,
            )
            object_key = self._storage.build_object_key(
                folder="documents", filename=f"agreement_{application.id}.pdf"
            )
            self._storage.put_object(
                object_key=object_key,
                content=pdf_bytes,
                content_type="application/pdf",
            )
            stored = StoredFile(
                object_key=object_key,
                original_filename=f"adoption_agreement_{application.id}.pdf",
                mime_type="application/pdf",
                file_size=len(pdf_bytes),
                folder=FileFolder.DOCUMENTS.value,
                is_uploaded=True,
                uploaded_at=datetime.now(UTC),
                entity_type="adoption_application",
                entity_id=application.id,
            )
            self._repo._session.add(stored)
            application.adoption_agreement_url = object_key
            await self._repo._session.flush()
            if self._audit:
                await self._audit.record(
                    event_type=AuthAuditEventType.ADOPTION_AGREEMENT_GENERATED,
                    actor_id=None,
                    ip_address="",
                    user_agent="",
                    metadata={
                        "adoption_id": str(application.id),
                        "dog_id": str(application.dog_id),
                    },
                )
        except Exception:
            logger.warning(
                "Failed to generate agreement for application %s", application.id, exc_info=True
            )

    @staticmethod
    def _check_transition(old_status: AdoptionStatus, new_status: AdoptionStatus) -> None:
        if old_status == new_status:
            return
        # old_status may come back as a plain str after a session refresh
        # (StrEnum hashes/compares equal to its string value either way, so
        # the dict lookup and comparisons above are safe) - coerce explicitly
        # before formatting so `.value` access below can't crash.
        old_status = AdoptionStatus(old_status)
        allowed = VALID_STATUS_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise ValidationFailedError(
                f"Cannot transition adoption application from '{old_status.value}' "
                f"to '{new_status.value}'."
            )

    async def apply_for_adoption(
        self,
        adopter_id: uuid.UUID,
        payload: AdoptionApplicationCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AdoptionApplication:
        # PRR 7.2 Zero Exclusivity Violation: always lock the dog row FIRST
        # via SELECT ... FOR UPDATE - this is the authoritative guarantee
        # against concurrent approvals on the same dog, independent of Redis.
        # The Redis lock below is a best-effort secondary guard to reduce
        # contention, but never the sole defense.
        dog = await self._dog_repo.get_by_id_for_update(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        if not dog.is_adoptable:
            raise ConflictError(
                f"Dog '{dog.name}' (ID: {payload.dog_id}) is not currently cleared for adoption."
            )

        existing_approved = await self._repo.get_approved_application_for_dog(payload.dog_id)
        if existing_approved is not None:
            raise ConflictError(
                f"Dog '{dog.name}' is already under an approved adoption process with another applicant."
            )

        existing_app = await self._repo.get_application_by_adopter_and_dog(
            adopter_id, payload.dog_id
        )
        if existing_app is not None:
            raise ConflictError(
                f"You have already submitted an active adoption application for dog '{dog.name}'."
            )

        # Best-effort Redis-side lock to reduce contention; the DB row lock
        # above is the real guarantee.
        lock_token = str(uuid.uuid4())
        lock_acquired = False
        cache_svc = None
        if self._redis is not None:
            cache_svc = CacheService(self._redis, namespace="adoptions")
            lock_acquired = await cache_svc.acquire_lock(
                f"lock:dog:{payload.dog_id}", lock_token, expire_ms=10000
            )
            if not lock_acquired:
                raise ConflictError(
                    f"Another applicant is currently processing an application for dog '{dog.name}'. Please try again in a few moments."
                )

        try:
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

            await self._notify_adopter(
                res,
                title=f"Adoption application received for {dog.name}",
                body=(
                    "Thank you for your interest in adopting "
                    f"{dog.name}. Our adoption team will review your "
                    "application and contact you for the next steps."
                ),
                notification_type="adoption_submitted",
                action_url="/adoptions/my-applications",
            )

            return res
        finally:
            if lock_acquired and cache_svc is not None:
                await cache_svc.release_lock(f"lock:dog:{payload.dog_id}", lock_token)


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
            self._check_transition(app.status, new_status)

            if new_status in (
                AdoptionStatus.HOME_CHECK, AdoptionStatus.APPROVED, AdoptionStatus.COMPLETED,
            ):
                lock_token = str(uuid.uuid4())
                lock_acquired = False
                cache_svc = None
                if self._redis is not None:
                    cache_svc = CacheService(self._redis, namespace="adoptions")
                    lock_acquired = await cache_svc.acquire_lock(
                        f"lock:dog:{app.dog_id}", lock_token, expire_ms=10000
                    )
                    if not lock_acquired:
                        raise ConflictError(
                            "This dog is currently being processed. Please try again later."
                        )

                try:
                    # Lock the dog row first: this serializes concurrent approvals
                    # for the same dog so the check-then-act below can't race.
                    dog = await self._dog_repo.get_by_id_for_update(app.dog_id)

                    existing_approved = await self._repo.get_approved_application_for_dog(app.dog_id)
                    if existing_approved is not None and existing_approved.id != app_id:
                        raise ConflictError(
                            "Another application has already reached home inspection or "
                            "approval for this dog."
                        )

                    if dog is not None:
                        dog.is_adoptable = False
                        if new_status == AdoptionStatus.COMPLETED:
                            dog.status = DogStatus.ADOPTED
                finally:
                    if lock_acquired and cache_svc is not None:
                        await cache_svc.release_lock(f"lock:dog:{app.dog_id}", lock_token)

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

        if res.status == AdoptionStatus.APPROVED and "status" in update_data:
            await self._generate_agreement(res)
            res = await self._repo.get_by_id(app_id)
            if res is None:
                raise NotFoundError("Adoption application not found after update.")

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
        self._check_transition(old_status, status)

        if status in (AdoptionStatus.HOME_CHECK, AdoptionStatus.APPROVED, AdoptionStatus.COMPLETED):
            lock_token = str(uuid.uuid4())
            lock_acquired = False
            cache_svc = None
            if self._redis is not None:
                cache_svc = CacheService(self._redis, namespace="adoptions")
                lock_acquired = await cache_svc.acquire_lock(
                    f"lock:dog:{app.dog_id}", lock_token, expire_ms=10000
                )
                if not lock_acquired:
                    raise ConflictError(
                        "This dog is currently being processed. Please try again later."
                    )

            try:
                # Lock the dog row first: this serializes concurrent approvals for
                # the same dog so the check-then-act below can't race.
                dog = await self._dog_repo.get_by_id_for_update(app.dog_id)

                existing_approved = await self._repo.get_approved_application_for_dog(app.dog_id)
                if existing_approved is not None and existing_approved.id != app_id:
                    raise ConflictError(
                        "Another application has already reached home inspection or "
                        "approval for this dog."
                    )

                if dog is not None:
                    dog.is_adoptable = False
                    if status == AdoptionStatus.COMPLETED:
                        dog.status = DogStatus.ADOPTED
            finally:
                if lock_acquired and cache_svc is not None:
                    await cache_svc.release_lock(f"lock:dog:{app.dog_id}", lock_token)


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
                    "old_status": AdoptionStatus(old_status).value,
                    "new_status": status.value,
                },
                # Structured before/after snapshots (audit finding #3):
                # transition origin/destination as queryable state, mirroring
                # the same values already carried in metadata.
                before_state={"status": AdoptionStatus(old_status).value},
                after_state={"status": status.value},
            )

        if status == AdoptionStatus.APPROVED and old_status != status:
            await self._generate_agreement(res)
            res = await self._repo.get_by_id(app_id)
            if res is None:
                raise NotFoundError("Adoption application not found after status update.")

        dog_name = res.dog.name if res.dog is not None else "your adopted dog"
        if status == AdoptionStatus.APPROVED and old_status != status:
            await self._notify_adopter(
                res,
                title=f"Great news - your adoption of {dog_name} is approved!",
                body=(
                    f"Congratulations! Your adoption of {dog_name} has been "
                    "approved. Our team will contact you to schedule the handover."
                ),
                notification_type="adoption_approved",
                action_url="/adoptions/my-applications",
            )
        elif status == AdoptionStatus.REJECTED and old_status != status:
            await self._notify_adopter(
                res,
                title=f"Update on your adoption application for {dog_name}",
                body=(
                    f"Thank you for applying to adopt {dog_name}. After careful "
                    "review, we are unable to proceed with your application at "
                    "this time. Please reach out if you have any questions."
                ),
                notification_type="adoption_rejected",
                action_url="/adoptions/my-applications",
            )
        elif status == AdoptionStatus.COMPLETED and old_status != status:
            await self._notify_adopter(
                res,
                title=f"Welcome {dog_name} to your family!",
                body=(
                    f"{dog_name} has been officially adopted by you. Thank you "
                    "for giving a rescued dog a loving home!"
                ),
                notification_type="adoption_completed",
                action_url="/adoptions/my-applications",
            )

        return res

    async def update_adoption_fee(
        self,
        app_id: uuid.UUID,
        fee_amount: Decimal,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AdoptionApplication:
        """Set the adoption fee before approval (audit finding: the agreement
        PDF used to hardcode 0.0 because no fee was ever stored)."""
        app = await self._repo.get_by_id(app_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")

        if app.status == AdoptionStatus.COMPLETED:
            raise ConflictError("Cannot update the fee after the adoption is completed.")

        app.fee_amount = Decimal(str(fee_amount)).quantize(Decimal("0.01"))
        await self._repo._session.flush()
        res = await self._repo.get_by_id(app_id)
        if res is None:
            raise NotFoundError("Adoption application not found after fee update.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADOPTION_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "adoption_id": str(app_id),
                    "fee_amount": str(app.fee_amount),
                },
            )

        return res

    async def get_follow_ups(self, app_id: uuid.UUID) -> list[AdoptionFollowUp]:
        app = await self._repo.get_by_id(app_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")
        return list(await self._repo.get_follow_ups_for_application(app_id))

    async def record_followup_proof(
        self,
        follow_up_id: uuid.UUID,
        media_keys: list[str] | None = None,
        notes: str | None = None,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AdoptionFollowUp:
        """Record the adopter's proof submission for a follow-up check-in."""
        follow_up = await self._repo.get_follow_up_by_id(follow_up_id)
        if follow_up is None:
            raise NotFoundError("Follow-up not found.")

        if follow_up.status == FollowUpStatus.SUBMITTED:
            raise ConflictError("This follow-up has already been submitted.")

        follow_up.status = FollowUpStatus.SUBMITTED
        follow_up.submitted_at = datetime.now(UTC)
        follow_up.media_keys = media_keys or []
        if notes is not None:
            follow_up.notes = notes

        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADOPTION_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "follow_up_id": str(follow_up_id),
                    "application_id": str(follow_up.adoption_application_id),
                    "media_keys": follow_up.media_keys or [],
                },
            )

        return follow_up

    async def find_due_follow_ups(
        self, now: datetime | None = None
    ) -> list[AdoptionFollowUp]:
        """Ensure every completed adoption has 30/90/180-day check-ins, mark
        due-but-unsubmitted ones OVERDUE, and return everything now due."""
        now = now or datetime.now(UTC)

        completed_apps = await self._repo.get_completed_applications()
        for app in completed_apps:
            if app.completed_at is None:
                continue
            for days in FOLLOW_UP_INTERVALS:
                existing = await self._repo.get_follow_up_for_milestone(app.id, days)
                if existing is None:
                    await self._repo.create_follow_up(
                        AdoptionFollowUp(
                            adoption_application_id=app.id,
                            due_day=days,
                            due_at=app.completed_at + timedelta(days=days),
                            status=FollowUpStatus.PENDING,
                        )
                    )

        due = list(await self._repo.get_due_follow_ups(now))
        for follow_up in due:
            if follow_up.status == FollowUpStatus.PENDING and follow_up.due_at < now:
                follow_up.status = FollowUpStatus.OVERDUE

        return due

    async def add_score(
        self,
        application_id: uuid.UUID,
        payload: AdoptionScoreCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AdoptionScore:
        app = await self._repo.get_by_id(application_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")

        total = (
            payload.home_environment_score
            + payload.pet_care_knowledge_score
            + payload.financial_readiness_score
            + payload.lifestyle_compatibility_score
        ) / 4.0

        score = AdoptionScore(
            application_id=application_id,
            scored_by_id=actor_id,
            home_environment_score=payload.home_environment_score,
            pet_care_knowledge_score=payload.pet_care_knowledge_score,
            financial_readiness_score=payload.financial_readiness_score,
            lifestyle_compatibility_score=payload.lifestyle_compatibility_score,
            overall_score=total,
            recommendation=payload.recommendation,
            notes=payload.notes,
            scored_at=datetime.now(UTC),
        )
        await self._repo.create_score(score)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADOPTION_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "adoption_id": str(application_id),
                    "score_id": str(score.id),
                    "overall_score": float(total),
                    "recommendation": payload.recommendation,
                },
            )

        return score

    async def get_scores(self, application_id: uuid.UUID) -> list[AdoptionScore]:
        app = await self._repo.get_by_id(application_id)
        if app is None:
            raise NotFoundError("Adoption application not found.")
        return list(await self._repo.get_scores_for_application(application_id))

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

    async def find_nearby_shelters(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[NearbyShelterResponse]:
        """Return shelters within ``radius_km`` of the adopter's location,
        nearest first, each bundled with its currently adoptable dogs.

        Used by the apply-for-adoption flow to let an adopter pick a dog
        that is near them. Reuses the shelter module's geospatial query so
        the haversine logic lives in exactly one place.
        """
        if self._shelter_repo is None:
            return []

        nearby = await self._shelter_repo.find_nearby_facilities(latitude, longitude, radius_km)
        if not nearby:
            return []

        facility_ids = [facility.id for facility, _distance in nearby]
        dogs = await self._shelter_repo.list_adoptable_dogs_by_facilities(facility_ids)

        dogs_by_facility: dict[uuid.UUID, list[DogProfile]] = {}
        for dog in dogs:
            dogs_by_facility.setdefault(dog.shelter_facility_id, []).append(dog)

        results: list[NearbyShelterResponse] = []
        for facility, distance_km in nearby:
            results.append(
                NearbyShelterResponse(
                    id=facility.id,
                    name=facility.name,
                    address=facility.address,
                    phone=facility.phone,
                    latitude=(
                        float(facility.latitude) if facility.latitude is not None else None
                    ),
                    longitude=(
                        float(facility.longitude) if facility.longitude is not None else None
                    ),
                    facility_type=facility.facility_type,
                    distance_km=distance_km,
                    adoptable_dogs=dogs_by_facility.get(facility.id) or [],
                )
            )
        return results

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
        # PRR 7.2 / 3.7: bulk updates to terminal states (HOME_CHECK / APPROVED
        # / COMPLETED) must go through the same exclusivity gate as the
        # single-application update path - otherwise a single staff action can
        # approve multiple applications for the same dog. Reject outright.
        if status in (
            AdoptionStatus.HOME_CHECK,
            AdoptionStatus.APPROVED,
            AdoptionStatus.COMPLETED,
        ):
            raise ValidationFailedError(
                f"Bulk update to '{status.value}' is not permitted. "
                "These terminal approval states must be applied per-application "
                "via update_application so the per-dog exclusivity check runs."
            )

        # For non-terminal bulk updates, still validate the state-machine
        # transition per application so a bulk action cannot short-circuit
        # SUBMITTED -> COMPLETED in one step.
        apps = await self._repo.get_by_ids(ids)
        for app in apps:
            self._check_transition(app.status, status)

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
        count = await self._repo.bulk_soft_delete(ids)

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
