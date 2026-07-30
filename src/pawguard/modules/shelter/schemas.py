"""Pydantic schemas for the Shelter & Capacity module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.shelter.models import (
    FacilityStatus,
    FacilityType,
    KennelSanitationState,
    TransferStatus,
)


class ShelterFacilityCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1, max_length=32)
    total_capacity: int = Field(50, ge=1)
    facility_type: FacilityType = Field(FacilityType.SHELTER)


class ShelterFacilityUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = Field(None, min_length=1)
    phone: str | None = Field(None, min_length=1, max_length=32)
    total_capacity: int | None = Field(None, ge=1)
    facility_type: FacilityType | None = None


class ShelterFacilityResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    phone: str
    total_capacity: int
    status: FacilityStatus
    facility_type: FacilityType
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FacilityStatusUpdate(BaseModel):
    status: FacilityStatus


class ShelterSectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    capacity: int = Field(10, ge=1)


class ShelterSectionResponse(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    name: str
    capacity: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KennelCreate(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=64)
    capacity: int = Field(1, ge=1)


class KennelResponse(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    identifier: str
    capacity: int
    sanitation_state: KennelSanitationState
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FacilityTransferCreate(BaseModel):
    dog_id: uuid.UUID
    from_facility_id: uuid.UUID
    to_facility_id: uuid.UUID
    notes: str | None = None


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
    dietary_requirements: str | None = None
    exercise_hours: float = Field(0.0, ge=0.0, le=24.0)
    behavioral_enrichment: str | None = None


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
