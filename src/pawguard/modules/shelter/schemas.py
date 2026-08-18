"""Pydantic schemas for the Shelter & Capacity module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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


class KennelResponse(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    identifier: str
    capacity: int
    sanitation_state: KennelSanitationState
    is_occupied: bool = False
    occupied_by_dog_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FacilityTransferCreate(BaseModel):
    dog_id: uuid.UUID
    from_facility_id: uuid.UUID
    to_facility_id: uuid.UUID
    notes: str | None = Field(None, examples=["Transferring for specialized surgical care."])


class FacilityTransferResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    from_facility_id: uuid.UUID
    to_facility_id: uuid.UUID
    transferred_by: uuid.UUID
    status: TransferStatus
    notes: str | None
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
