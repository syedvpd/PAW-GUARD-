"""Pydantic schemas for the Dog Management module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.dog.models import (
    DogActivityEventType,
    DogBreedClassification,
    DogEarShape,
    DogGender,
    DogStatus,
    DogTailType,
    DogTemperament,
)


class DogProfileCreate(BaseModel):
    rescue_case_id: uuid.UUID | None = None
    microchip_id: str | None = Field(None, max_length=64, examples=["985141002345678"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Barnaby"])
    breed: str = Field("indie_mix", max_length=128, examples=["Indie Mix"])
    breed_classification: DogBreedClassification | None = Field(
        None, description="Pure/Mix/Unknown; inferred from breed when omitted."
    )
    gender: DogGender = DogGender.UNKNOWN
    is_spayed_neutered: bool = False
    estimated_age: str | None = Field(None, max_length=64, examples=["2 years"])
    age_months: int | None = Field(
        None, ge=0, le=600, description="Derived from estimated_age when omitted."
    )
    weight: float | None = Field(None, ge=0.0, examples=[16.4])
    color: str | None = Field(None, max_length=64, examples=["Tan/White"])
    temperament: DogTemperament | None = Field(None, examples=["friendly"])
    ear_shape: DogEarShape | None = Field(None, examples=["floppy"])
    tail_type: DogTailType | None = Field(None, examples=["curled"])
    distinctive_markers: str | None = Field(
        None, max_length=512, examples=["White patch on chest, notched left ear"]
    )
    shelter_facility_id: uuid.UUID | None = None
    section_id: uuid.UUID | None = None
    kennel_id: uuid.UUID | None = None
    foster_home_id: uuid.UUID | None = None
    is_adoptable: bool = False
    is_quarantine_passed: bool = False


class DogProfileUpdate(BaseModel):
    microchip_id: str | None = Field(None, examples=["985141002345678"])
    name: str | None = Field(None, examples=["Barnaby"])
    breed: str | None = Field(None, examples=["Indie Mix"])
    breed_classification: DogBreedClassification | None = Field(
        None, description="Pure/Mix/Unknown; re-inferred when breed changes."
    )
    gender: DogGender | None = Field(None, examples=["male"])
    is_spayed_neutered: bool | None = Field(None, examples=[True])
    estimated_age: str | None = Field(None, examples=["2 years"])
    age_months: int | None = Field(
        None, ge=0, le=600, description="Re-derived from estimated_age when null."
    )
    weight: float | None = Field(None, examples=[16.4])
    color: str | None = Field(None, examples=["Tan/White"])
    temperament: DogTemperament | None = Field(None, examples=["friendly"])
    ear_shape: DogEarShape | None = Field(None, examples=["floppy"])
    tail_type: DogTailType | None = Field(None, examples=["curled"])
    distinctive_markers: str | None = Field(
        None, max_length=512, examples=["White patch on chest"]
    )
    status: DogStatus | None = Field(None, examples=["shelter"])
    shelter_facility_id: uuid.UUID | None = None
    section_id: uuid.UUID | None = None
    kennel_id: uuid.UUID | None = None
    foster_home_id: uuid.UUID | None = None
    is_adoptable: bool | None = Field(None, examples=[False])
    is_quarantine_passed: bool | None = Field(None, examples=[True])


class DogStatusUpdate(BaseModel):
    status: DogStatus = Field(..., description="New status for the dog", examples=["shelter"])


class DogProfileResponse(BaseModel):
    id: uuid.UUID
    registration_number: str
    rescue_case_id: uuid.UUID | None
    microchip_id: str | None
    name: str
    breed: str
    breed_classification: DogBreedClassification
    gender: DogGender
    is_spayed_neutered: bool
    estimated_age: str | None
    age_months: int | None
    weight: float | None
    color: str | None
    temperament: DogTemperament | None
    ear_shape: DogEarShape | None
    tail_type: DogTailType | None
    distinctive_markers: str | None
    status: DogStatus
    shelter_facility_id: uuid.UUID | None
    section_id: uuid.UUID | None
    kennel_id: uuid.UUID | None
    foster_home_id: uuid.UUID | None
    is_adoptable: bool
    is_quarantine_passed: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DogListQueryParams(BaseModel):
    """Public adoption-directory filters (PRR 3.1.4: age, size, temperaments,
    location) plus staff-facing registry filters."""

    search: str | None = Field(None, description="Search by name, breed, registration number")
    status: DogStatus | None = None
    is_adoptable: bool | None = None
    breed: str | None = None
    breed_classification: DogBreedClassification | None = None
    gender: DogGender | None = None
    temperament: DogTemperament | None = None
    min_age_months: int | None = Field(None, ge=0, description="Minimum age in months")
    max_age_months: int | None = Field(None, ge=0, description="Maximum age in months")
    min_weight: float | None = Field(None, ge=0.0, description="Minimum weight in kg")
    max_weight: float | None = Field(None, ge=0.0, description="Maximum weight in kg")
    location: str | None = Field(
        None, description="Free-text match on the shelter facility name/address"
    )


class DogWeightLogCreate(BaseModel):
    """One weight measurement for a dog (PRR 3.4 Weight History)."""

    weight: float = Field(..., gt=0, le=2000, description="Weight in kg", examples=[16.4])
    measured_at: datetime | None = Field(
        None, description="Defaults to now when omitted."
    )
    notes: str | None = Field(None, max_length=512, examples=["Post-surgery weigh-in"])


class DogWeightLogResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    measured_by: uuid.UUID | None
    weight: float
    measured_at: datetime
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DogActivityLogResponse(BaseModel):
    """One immutable entry in a dog's lifecycle activity stream (PRR 3.4)."""

    id: uuid.UUID
    dog_id: uuid.UUID
    actor_id: uuid.UUID | None
    event_type: DogActivityEventType
    message: str
    event_metadata: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
