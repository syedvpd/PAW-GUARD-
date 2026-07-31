"""Pydantic schemas for the Dog Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.dog.models import DogStatus


class DogProfileCreate(BaseModel):
    rescue_case_id: uuid.UUID | None = None
    microchip_id: str | None = Field(None, max_length=64, examples=["985141002345678"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Barnaby"])
    breed: str = Field("indie_mix", max_length=128, examples=["Indie Mix"])
    gender: str = Field(..., min_length=4, max_length=16, examples=["male"])
    is_spayed_neutered: bool = False
    estimated_age: str | None = Field(None, max_length=64, examples=["2 years"])
    weight: float | None = Field(None, ge=0.0, examples=[16.4])
    color: str | None = Field(None, max_length=64, examples=["Tan/White"])
    temperament: str | None = Field(None, max_length=64, examples=["Friendly"])
    shelter_facility_id: uuid.UUID | None = None
    kennel_id: uuid.UUID | None = None
    is_adoptable: bool = False
    is_quarantine_passed: bool = False


class DogProfileUpdate(BaseModel):
    microchip_id: str | None = Field(None, examples=["985141002345678"])
    name: str | None = Field(None, examples=["Barnaby"])
    breed: str | None = Field(None, examples=["Indie Mix"])
    gender: str | None = Field(None, examples=["male"])
    is_spayed_neutered: bool | None = Field(None, examples=[True])
    estimated_age: str | None = Field(None, examples=["2 years"])
    weight: float | None = Field(None, examples=[16.4])
    color: str | None = Field(None, examples=["Tan/White"])
    temperament: str | None = Field(None, examples=["Friendly"])
    status: DogStatus | None = Field(None, examples=["shelter"])
    shelter_facility_id: uuid.UUID | None = None
    kennel_id: uuid.UUID | None = None
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
