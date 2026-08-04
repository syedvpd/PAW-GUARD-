"""DogService: owns all dog profile and lifecycle business behavior (RULE-003)."""

import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import (
    DogActivityEventType,
    DogActivityLog,
    DogBreedClassification,
    DogProfile,
    DogStatus,
    DogWeightLog,
)
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import (
    DogProfileCreate,
    DogProfileResponse,
    DogProfileUpdate,
    DogWeightLogCreate,
)
from pawguard.services.audit_service import AuditService

# DOG-YYYY-NNNN leaves only 10,000 numbers per year, so collisions are
# possible under concurrent intake; retry a bounded number of times before
# giving up cleanly (mirrors the rescue module's ticket-number handling).
_MAX_REGISTRATION_RETRIES = 5

# ISO 11784/11785 microchips are 15 digits; a leading "985" registrar prefix
# is the common global code, so synthesized chips read like real ones.
_MICROCHIP_PREFIX = "985"
_MICROCHIP_SUFFIX_DIGITS = 12


def _generate_microchip_id() -> str:
    """Synthesize a unique 15-digit microchip number for a newly registered
    dog (PRR 3.4 System IDs). Real chips are implanted by a vet; PawGuard
    generates its own registration value so every intake has one."""
    suffix = "".join(secrets.choice("0123456789") for _ in range(_MICROCHIP_SUFFIX_DIGITS))
    return f"{_MICROCHIP_PREFIX}{suffix}"


# Keywords that mark a free-text breed as a mix (PRR 3.4 Demographics:
# Breed classification Pure/Mix/Unknown). Anything without these markers is
# conservatively classified Unknown - asserting "pure" from free text is
# unreliable, so staff can correct it explicitly via the API.
_MIX_BREED_KEYWORDS = ("mix", "cross", "mongrel", "indie")

# Matches the leading number in free-text ages like "2 years", "6 months",
# "2-year-old". Anchored to the string start (allowing an optional hyphen)
# so "2.5 years" / "12-18 months" are rejected as unparseable instead of
# silently extracting "5 years"/"18 months" - consistent with the migration's
# anchored backfill, and unparseable rows are excluded from filters rather
# than mis-filtered (PRR 3.1.4).
_AGE_NUMBER_RE = re.compile(r"^\s*(\d+)\s*-?\s*(year|month|yr|mo)", re.IGNORECASE)


def _infer_breed_classification(breed: str) -> DogBreedClassification:
    """Best-effort Pure/Mix/Unknown classification from free-text breed."""
    lowered = breed.lower()
    if any(k in lowered for k in _MIX_BREED_KEYWORDS):
        return DogBreedClassification.MIX
    return DogBreedClassification.UNKNOWN


def _parse_age_months(estimated_age: str | None) -> int | None:
    """Derive a numeric age in months from free-text estimated_age
    (PRR 3.1.4 age filter). Unparseable values return None so filtering
    simply excludes the dog instead of failing."""
    if not estimated_age:
        return None
    match = _AGE_NUMBER_RE.search(estimated_age)
    if match is None:
        return None
    # First match wins, so a compound "1 year 6 months" parses as 12 months -
    # a conservative under-estimate rather than a wrong over-estimate. This
    # matches the migration's best-effort backfill, which only handles simple
    # "N year(s)" / "N month(s)" strings (and not "yr"/"mo" abbreviations).
    number = int(match.group(1))
    unit = match.group(2).lower()
    if unit in ("year", "yr"):
        return number * 12
    if unit in ("month", "mo"):
        return number
    return None


async def record_activity(
    session: AsyncSession,
    *,
    dog_id: uuid.UUID,
    event_type: DogActivityEventType | str,
    actor_id: uuid.UUID | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DogActivityLog:
    """Append an immutable row to a dog's activity stream (PRR 3.4).

    Reusable across modules: any domain that mutates a dog's lifecycle
    (adoption, foster, shelter, medical, transfers, ...) can import this and
    write to the stream without reaching into dog internals. The row is
    appended to ``session`` and flushed; the caller owns the transaction.

    ``event_type`` conventions:
      - Dog-module events use the ``DogActivityEventType`` members
        (REGISTERED, UPDATED, STATUS_CHANGED, DELETED, WEIGHT_RECORDED,
        BULK_STATUS_UPDATED, BULK_DELETED).
      - Cross-module lifecycle events should pass a descriptive snake_case
        string so the stream reads as one chronological trail, e.g.
        "transfer_created", "transfer_confirmed", "foster_placed",
        "foster_ended", "adoption_application_submitted",
        "adoption_completed", "medical_record_created",
        "post_adoption_inspection_submitted". Prefer a single past-tense
        verb + object phrase.
    ``message`` defaults to a human-readable "<event>." line when the caller
    does not supply one. Rows are never updated or deleted.
    """
    if message is None:
        value = event_type.value if isinstance(event_type, DogActivityEventType) else event_type
        message = f"{value.replace('_', ' ')}."
    repo = DogRepository(session)
    return await repo.create_activity(
        DogActivityLog(
            dog_id=dog_id,
            actor_id=actor_id,
            event_type=event_type,
            message=message,
            event_metadata=metadata,
        )
    )


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
        # Prevent duplicate intake (PRR 3.4): before allocating identifiers,
        # reject a dog that already exists in the registry with the same
        # identifying details.
        duplicate = await self._repo.get_duplicate_by_details(
            name=payload.name,
            breed=payload.breed,
            gender=payload.gender,
            color=payload.color,
            distinctive_markers=payload.distinctive_markers,
        )
        if duplicate is not None:
            raise ConflictError(
                "A dog with these details (name, breed, gender, color) is already registered."
            )

        if payload.microchip_id:
            existing_chip = await self._repo.get_by_microchip(payload.microchip_id)
            if existing_chip is not None:
                raise ConflictError("A dog with this microchip ID is already registered.")
            microchip_id = payload.microchip_id
        else:
            microchip_id = await self._allocate_microchip_id()

        dog: DogProfile | None = None
        for _ in range(_MAX_REGISTRATION_RETRIES):
            year_str = datetime.now(UTC).strftime("%Y")
            rand_suffix = "".join(secrets.choice("0123456789") for _ in range(4))
            registration_number = f"DOG-{year_str}-{rand_suffix}"

            # Fast path: skip an already-taken number without a DB error.
            if await self._repo.get_by_registration(registration_number) is not None:
                continue

            dog = DogProfile(
                registration_number=registration_number,
                rescue_case_id=payload.rescue_case_id,
                microchip_id=microchip_id,
                name=payload.name,
                breed=payload.breed,
                breed_classification=(
                    payload.breed_classification
                    or _infer_breed_classification(payload.breed)
                ),
                gender=payload.gender,
                is_spayed_neutered=payload.is_spayed_neutered,
                estimated_age=payload.estimated_age,
                age_months=(
                    payload.age_months
                    if payload.age_months is not None
                    else _parse_age_months(payload.estimated_age)
                ),
                weight=payload.weight,
                color=payload.color,
                temperament=payload.temperament,
                ear_shape=payload.ear_shape,
                tail_type=payload.tail_type,
                distinctive_markers=payload.distinctive_markers,
                status=DogStatus.RESCUED,
                shelter_facility_id=payload.shelter_facility_id,
                section_id=payload.section_id,
                kennel_id=payload.kennel_id,
                foster_home_id=payload.foster_home_id,
                # is_adoptable is never set from client input: a dog can only be
                # marked adoptable via the vet-authorized medical clearance flow
                # (POST /medical/clearance/{dog_id}), never at registration.
                is_adoptable=False,
                is_quarantine_passed=payload.is_quarantine_passed,
            )
            try:
                dog = await self._repo.create(dog)
            except IntegrityError:
                # A concurrent request claimed the same registration number
                # between the existence check and the flush - roll back and
                # retry with a fresh suffix.
                await self._repo._session.rollback()
                continue
            break

        if dog is None:
            raise ConflictError(
                "Unable to allocate a unique dog registration number. Please retry."
            )

        await self._record_activity(
            dog_id=dog.id,
            event_type=DogActivityEventType.REGISTERED,
            message=f"Dog registered with number {dog.registration_number}.",
            actor_id=actor_id,
            metadata={"registration_number": dog.registration_number},
        )

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DOG_REGISTERED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"dog_id": str(dog.id), "registration_number": registration_number},
            )

        return dog

    async def _allocate_microchip_id(self) -> str:
        """Generate a unique 15-digit microchip id, retrying on the rare
        collision (PRR 3.4 System IDs). Fails cleanly instead of surfacing a
        UNIQUE constraint 500."""
        for _ in range(_MAX_REGISTRATION_RETRIES):
            candidate = _generate_microchip_id()
            if await self._repo.get_by_microchip(candidate) is None:
                return candidate
        raise ConflictError("Unable to allocate a unique microchip ID. Please retry.")

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
        if update_data.get("is_adoptable") is True and not dog.is_adoptable:
            raise ForbiddenError(
                "is_adoptable can only be granted via the veterinarian-authorized "
                "medical clearance endpoint (POST /medical/clearance/{dog_id})."
            )
        # Microchip is UNIQUE: re-assigning it to another dog is a conflict,
        # not a 500 from the constraint violation.
        new_chip = update_data.get("microchip_id")
        if new_chip and new_chip != dog.microchip_id:
            existing_chip = await self._repo.get_by_microchip(new_chip)
            if existing_chip is not None:
                raise ConflictError("A dog with this microchip ID is already registered.")

        # When the breed changes and no explicit classification was sent,
        # re-infer it so the profile never shows a stale Pure/Mix label
        # (PRR 3.4 breed classification). An explicit null also means
        # "auto-infer": the column is NOT NULL, so a bare None would surface
        # as a constraint violation on flush.
        if "breed_classification" in update_data:
            if update_data["breed_classification"] is None:
                update_data["breed_classification"] = _infer_breed_classification(
                    update_data.get("breed", dog.breed)
                )
        elif "breed" in update_data:
            update_data["breed_classification"] = _infer_breed_classification(
                update_data["breed"]
            )

        # age_months stays consistent with estimated_age: an explicit null
        # means "re-derive", and an age-only edit re-derives the numeric value
        # so the directory's age-range filter stays accurate (PRR 3.1.4).
        if "age_months" in update_data:
            if update_data["age_months"] is None:
                update_data["age_months"] = _parse_age_months(
                    update_data.get("estimated_age", dog.estimated_age)
                )
        elif "estimated_age" in update_data:
            update_data["age_months"] = _parse_age_months(
                update_data["estimated_age"]
            )

        original_weight = dog.weight
        for key, value in update_data.items():
            setattr(dog, key, value)

        # A weight edit through the profile must also append to the weight
        # history (PRR 3.4) - otherwise the profile's "current weight" can
        # diverge from the trend recorded by POST /dogs/{id}/weight.
        new_weight = update_data.get("weight")
        if new_weight is not None and new_weight != original_weight:
            await self._repo.create_weight_log(
                DogWeightLog(
                    dog_id=dog.id,
                    measured_by=actor_id,
                    weight=new_weight,
                    measured_at=datetime.now(UTC),
                    notes="Updated via profile edit",
                )
            )

        await self._repo._session.flush()
        await self._repo._session.refresh(dog)

        await self._record_activity(
            dog_id=dog.id,
            event_type=DogActivityEventType.UPDATED,
            message=f"Dog profile updated ({', '.join(sorted(update_data))}).",
            actor_id=actor_id,
            metadata={"changes": update_data},
        )

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

        # old_status is a DB-loaded plain string (String column, not a DB enum),
        # so str() - not .value - is the correct accessor for both states.
        await self._record_activity(
            dog_id=dog.id,
            event_type=DogActivityEventType.STATUS_CHANGED,
            message=f"Status changed from '{old_status}' to '{status.value}'.",
            actor_id=actor_id,
            metadata={"old_status": str(old_status), "new_status": status.value},
        )

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DOG_STATUS_CHANGED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "dog_id": str(dog_id),
                    "old_status": str(old_status),
                    "new_status": str(status),
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

        await self._record_activity(
            dog_id=dog.id,
            event_type=DogActivityEventType.DELETED,
            message=f"Dog profile soft-deleted (registration {dog.registration_number}).",
            actor_id=actor_id,
        )

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
        breed_classification: DogBreedClassification | None = None,
        gender: str | None = None,
        temperament: str | None = None,
        min_age_months: int | None = None,
        max_age_months: int | None = None,
        min_weight: float | None = None,
        max_weight: float | None = None,
        location: str | None = None,
    ) -> PaginatedResponse[DogProfileResponse]:
        results, total = await self._repo.list_paginated(
            page=page,
            sort=sort,
            search_term=search_term,
            status=status,
            is_adoptable=is_adoptable,
            breed=breed,
            breed_classification=breed_classification,
            gender=gender,
            temperament=temperament,
            min_age_months=min_age_months,
            max_age_months=max_age_months,
            min_weight=min_weight,
            max_weight=max_weight,
            location=location,
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

        # Only record timeline entries for dogs that actually exist and weren't
        # soft-deleted: list_by_ids filters deleted_at, and recording for a
        # nonexistent id would flush a dangling dog_id FK (IntegrityError 500).
        existing = await self._repo.list_by_ids(ids)
        for dog in existing:
            await self._record_activity(
                dog_id=dog.id,
                event_type=DogActivityEventType.BULK_STATUS_UPDATED,
                message=f"Status updated to '{status.value}' via bulk operation.",
                actor_id=actor_id,
                metadata={"status": status.value},
            )

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
        # Capture the eligible dogs BEFORE the delete: list_by_ids filters
        # deleted_at.is_(None), so querying afterwards would return an empty
        # set and the DELETED timeline entries would silently never be written.
        existing = await self._repo.list_by_ids(ids)

        count = await self._repo.bulk_soft_delete(ids)
        await self._repo._session.flush()

        for dog in existing:
            await self._record_activity(
                dog_id=dog.id,
                event_type=DogActivityEventType.BULK_DELETED,
                message="Dog soft-deleted via bulk operation.",
                actor_id=actor_id,
            )

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.BULK_DOG_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"dog_ids": [str(i) for i in ids], "count": count},
            )

        return count

    async def get_dog_timeline(self, dog_id: uuid.UUID) -> list[DogActivityLog]:
        """Chronological lifecycle stream for a dog's master profile (PRR 3.4).

        Uses get_any_by_id so the trail stays readable after soft-deletion -
        the stream is the permanent audit record "through final resolution".
        """
        dog = await self._repo.get_any_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")
        logs = await self._repo.list_activity_by_dog(dog_id)
        return list(logs)

    # --- Weight history (PRR 3.4: Demographics - Weight History) ---

    async def record_weight(
        self,
        dog_id: uuid.UUID,
        payload: DogWeightLogCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> DogWeightLog:
        """Append a weight measurement and refresh the profile's current
        weight (the profile holds the latest measurement, the log the trend).
        """
        dog = await self.get_dog(dog_id)
        measured_at = payload.measured_at or datetime.now(UTC)

        log = DogWeightLog(
            dog_id=dog.id,
            measured_by=actor_id,
            weight=payload.weight,
            measured_at=measured_at,
            notes=payload.notes,
        )
        await self._repo.create_weight_log(log)

        dog.weight = payload.weight
        await self._repo._session.flush()
        await self._repo._session.refresh(dog)

        await self._record_activity(
            dog_id=dog.id,
            event_type=DogActivityEventType.WEIGHT_RECORDED,
            message=f"Weight recorded: {payload.weight} kg.",
            actor_id=actor_id,
            metadata={
                "weight": payload.weight,
                "measured_at": measured_at.isoformat(),
                "notes": payload.notes,
            },
        )

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DOG_WEIGHT_RECORDED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "dog_id": str(dog_id),
                    "weight": payload.weight,
                    "measured_at": measured_at.isoformat(),
                },
            )

        return log

    async def get_weight_history(
        self, dog_id: uuid.UUID
    ) -> list[DogWeightLog]:
        """Chronological weight measurements for a dog (PRR 3.4)."""
        dog = await self.get_dog(dog_id)
        logs = await self._repo.list_weight_logs(dog.id)
        return list(logs)

    async def _record_activity(
        self,
        *,
        dog_id: uuid.UUID,
        event_type: DogActivityEventType,
        message: str,
        actor_id: uuid.UUID | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if message is None:
            value = event_type.value if isinstance(event_type, DogActivityEventType) else event_type
            message = f"{value.replace('_', ' ')}."
        await self._repo.create_activity(
            DogActivityLog(
                dog_id=dog_id,
                actor_id=actor_id,
                event_type=event_type,
                message=message,
                event_metadata=metadata,
            )
        )
