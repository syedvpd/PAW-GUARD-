"""Pydantic schemas for the Shelter & Capacity module."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pawguard.modules.dog.models import DogGender, DogStatus, DogTemperament
from pawguard.modules.inventory.schemas import InventoryConsumptionItem
from pawguard.modules.shelter.models import (
    FacilityStatus,
    FacilityType,
    KennelSanitationState,
    SectionType,
    TransferStatus,
)


class ShelterFacilityCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Central Shelter Alpha"])
    address: str = Field(..., min_length=1, examples=["45 Rescue Road, Sector 4"])
    phone: str = Field(..., min_length=1, max_length=32, examples=["+1-555-0111"])
    latitude: float | None = Field(None, ge=-90.0, le=90.0, examples=[28.6139])
    longitude: float | None = Field(None, ge=-180.0, le=180.0, examples=[77.2090])
    total_capacity: int = Field(50, ge=1, examples=[100])
    facility_type: FacilityType = Field(FacilityType.SHELTER, examples=["shelter"])


class ShelterFacilityUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255, examples=["Central Shelter Alpha"])
    address: str | None = Field(None, min_length=1, examples=["45 Rescue Road, Sector 4"])
    phone: str | None = Field(None, min_length=1, max_length=32, examples=["+1-555-0111"])
    latitude: float | None = Field(None, ge=-90.0, le=90.0, examples=[28.6139])
    longitude: float | None = Field(None, ge=-180.0, le=180.0, examples=[77.2090])
    total_capacity: int | None = Field(None, ge=1, examples=[120])
    facility_type: FacilityType | None = Field(None, examples=["shelter"])


class ShelterFacilityResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    phone: str
    latitude: float | None
    longitude: float | None
    total_capacity: int
    status: FacilityStatus
    facility_type: FacilityType
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FacilityStatusUpdate(BaseModel):
    status: FacilityStatus = Field(..., examples=["active"])


class ShelterSectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, examples=["Quarantine"])
    section_type: SectionType = Field(SectionType.GENERAL, examples=["general"])
    capacity: int = Field(10, ge=1, examples=[15])


class ShelterSectionResponse(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    name: str
    section_type: SectionType
    capacity: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KennelCreate(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=64, examples=["K-08"])
    capacity: int = Field(1, ge=1, examples=[2])


class KennelAssignmentRequest(BaseModel):
    """Optional body for assigning a dog to a kennel.

    Quarantine/Isolation/Surgical sections normally require a veterinarian
    (PRR master-spec rule). A Shelter Manager can force the assignment in a
    genuine emergency (no vet immediately available) via emergency_override,
    with a mandatory justification note — flagged for vet review rather than
    a silent bypass. Optional so the endpoint stays backward compatible with
    a bodyless call for the common (non-clinical, or vet-authored) case.
    """

    emergency_override: bool = False
    override_notes: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _require_override_justification(self) -> "KennelAssignmentRequest":
        if self.emergency_override and not (self.override_notes and self.override_notes.strip()):
            raise ValueError("override_notes is required when emergency_override is set.")
        return self


class KennelResponse(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    identifier: str
    capacity: int
    sanitation_state: KennelSanitationState
    is_occupied: bool = False
    occupied_by_dog_id: uuid.UUID | None = None
    is_reserved_for_transfer: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SuggestedQuarantineKennelResponse(BaseModel):
    """A suggested (not assigned) Quarantine kennel for the intake screen to
    pre-fill; staff must still confirm via the normal assign endpoint."""

    kennel_id: uuid.UUID
    kennel_identifier: str
    section_id: uuid.UUID
    facility_id: uuid.UUID


class FacilityTransferCreate(BaseModel):
    dog_id: uuid.UUID
    from_facility_id: uuid.UUID
    to_facility_id: uuid.UUID
    notes: str | None = Field(None, examples=["Transferring for specialized surgical care."])
    destination_kennel_id: uuid.UUID | None = Field(
        None,
        description="Must be an Open + Clean kennel belonging to to_facility_id. "
        "Soft-locked against other pending transfers the instant this is created.",
    )
    vehicle_id: uuid.UUID | None = Field(
        None, description="Optional Fleet vehicle for the handoff."
    )


class FacilityTransferCancel(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000, examples=["Dog too unwell to travel."])


class FacilityTransferResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    from_facility_id: uuid.UUID
    to_facility_id: uuid.UUID
    transferred_by: uuid.UUID
    status: TransferStatus
    notes: str | None
    cancel_reason: str | None
    destination_kennel_id: uuid.UUID | None
    origin_kennel_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
    sender_confirmed_at: datetime | None
    sender_confirmed_by: uuid.UUID | None
    receiver_confirmed_at: datetime | None
    receiver_confirmed_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DailyCareLogCreate(BaseModel):
    dog_id: uuid.UUID
    dietary_requirements: str | None = Field(
        None, examples=["Grain-free diet, small portions 3x daily"]
    )
    exercise_hours: float = Field(0.0, ge=0.0, le=24.0, examples=[1.5])
    behavioral_enrichment: str | None = Field(None, examples=["Puzzle feeder, 20 min outdoor play"])
    inventory_consumptions: list[InventoryConsumptionItem] | None = Field(
        None, examples=[[{"item_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "quantity": 1.0}]]
    )


class DailyCareLogResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    logged_by: uuid.UUID
    feed_time: datetime
    dietary_requirements: str | None
    exercise_hours: float
    behavioral_enrichment: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KennelCleaningLogCreate(BaseModel):
    method: str | None = Field(None, min_length=1, max_length=64, examples=["pressure wash"])
    notes: str | None = Field(None, examples=["Full disinfection after parvo case."])


class KennelCleaningLogResponse(BaseModel):
    id: uuid.UUID
    kennel_id: uuid.UUID
    cleaned_by: uuid.UUID
    cleaned_at: datetime
    sanitation_state_after: KennelSanitationState
    cleaning_method: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NearbyShelterDogResponse(BaseModel):
    """Adoptable dog summary returned inside a nearby shelter result.

    A public subset of the dog profile: microchip / case / facility references
    are never exposed through the adoption lookup.
    """

    id: uuid.UUID
    registration_number: str
    name: str
    breed: str
    gender: DogGender
    is_spayed_neutered: bool
    estimated_age: str | None
    age_months: int | None
    weight: float | None
    color: str | None
    temperament: DogTemperament | None
    status: DogStatus
    is_adoptable: bool

    model_config = ConfigDict(from_attributes=True)


class NearbyShelterResponse(BaseModel):
    """A shelter located within the requested radius, sorted by distance.

    ``adoptable_dogs`` lists the adoptable dogs currently assigned to the
    shelter so adopters can browse matches directly from the nearest list.
    """

    id: uuid.UUID
    name: str
    address: str
    phone: str
    latitude: float | None
    longitude: float | None
    facility_type: FacilityType
    distance_km: float = Field(..., ge=0.0, examples=[2.4])
    adoptable_dogs: list[NearbyShelterDogResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ShelterVetCheckRequest(BaseModel):
    """Request body for POST /shelter/dogs/{dog_id}/request-vet-check."""

    vet_id: uuid.UUID = Field(..., description="UUID of the assigned veterinarian")
    reason: str = Field(..., min_length=1, description="Reason for the veterinary examination")
    notes: str | None = Field(None, description="Additional notes for the veterinarian")
    urgency: Literal["routine", "urgent", "emergency"] = Field(
        "routine", description="Urgency level of the request"
    )

    @field_validator("urgency", mode="before")
    @classmethod
    def normalize_urgency(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ("routine", "urgent", "emergency"):
                return v_clean
        return "routine"


class ShelterVetCheckResponse(BaseModel):
    """Response body for a created shelter vet check request."""

    id: uuid.UUID
    dog_id: uuid.UUID
    shelter_facility_id: uuid.UUID
    vet_id: uuid.UUID
    requested_by_id: uuid.UUID
    reason: str
    notes: str | None
    urgency: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ShelterVetRequestListResponse(BaseModel):
    """A single shelter vet request enriched with dog and requester info for list views."""

    id: uuid.UUID
    dog_id: uuid.UUID
    dog_name: str
    shelter_facility_id: uuid.UUID
    shelter_facility_name: str
    vet_id: uuid.UUID
    vet_name: str
    requested_by_id: uuid.UUID
    requester_name: str
    reason: str
    notes: str | None
    urgency: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
