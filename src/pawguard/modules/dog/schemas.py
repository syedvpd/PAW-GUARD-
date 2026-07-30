"""Pydantic schemas for the Dog Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.dog.models import DogStatus


class DogProfileCreate(BaseModel):
    rescue_case_id: uuid.UUID | None = None
    microchip_id: str | None = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    breed: str = Field("indie_mix", max_length=128)
    gender: str = Field(..., min_length=4, max_length=16)
    is_spayed_neutered: bool = False
    estimated_age: str | None = Field(None, max_length=64)
    weight: float | None = Field(None, ge=0.0)
    color: str | None = Field(None, max_length=64)
    temperament: str | None = Field(None, max_length=64)
    shelter_facility_id: uuid.UUID | None = None
    kennel_id: uuid.UUID | None = None
    is_adoptable: bool = False
    is_quarantine_passed: bool = False


class DogProfileUpdate(BaseModel):
    microchip_id: str | None = None
    name: str | None = None
    breed: str | None = None
    gender: str | None = None
    is_spayed_neutered: bool | None = None
    estimated_age: str | None = None
    weight: float | None = None
    color: str | None = None
    temperament: str | None = None
    status: DogStatus | None = None
    shelter_facility_id: uuid.UUID | None = None
    kennel_id: uuid.UUID | None = None
    is_adoptable: bool | None = None
    is_quarantine_passed: bool | None = None


class DogStatusUpdate(BaseModel):
    status: DogStatus = Field(..., description="New status for the dog")


class DogProfileResponse(BaseModel):
    id: uuid.UUID
    registration_number: str
    rescue_case_id: uuid.UUID | None
    microchip_id: str | None
    name: str
    breed: str
    gender: str
    is_spayed_neutered: bool
    estimated_age: str | None
    weight: float | None
    color: str | None
    temperament: str | None
    status: DogStatus
    shelter_facility_id: uuid.UUID | None
    kennel_id: uuid.UUID | None
    is_adoptable: bool
    is_quarantine_passed: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DogListQueryParams(BaseModel):
    search: str | None = Field(None, description="Search by name, breed, registration number")
    status: DogStatus | None = None
    is_adoptable: bool | None = None
    breed: str | None = None
    gender: str | None = None
    temperament: str | None = None
