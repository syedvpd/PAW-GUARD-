"""Pydantic schemas for the Adoption Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.adoption.models import AdoptionStatus
from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse


class AdoptionApplicationCreate(BaseModel):
    dog_id: uuid.UUID
    residential_status: str = Field(..., min_length=3, max_length=32)  # owned, rented
    has_landlord_approval: bool = False
    has_yard_fence: bool = False
    household_members_count: int = Field(1, ge=1)
    existing_pets_medical_details: str | None = None
    pet_care_experience: str | None = None


class AdoptionApplicationUpdate(BaseModel):
    status: AdoptionStatus | None = None
    vetting_officer_notes: str | None = None
    home_inspection_scheduled_at: datetime | None = None
    home_inspection_notes: str | None = None
    adoption_agreement_url: str | None = None


class AdoptionStatusUpdate(BaseModel):
    status: AdoptionStatus = Field(..., description="New status for the adoption application")


class AdoptionApplicationResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    adopter_id: uuid.UUID
    status: AdoptionStatus
    residential_status: str
    has_landlord_approval: bool
    has_yard_fence: bool
    household_members_count: int
    existing_pets_medical_details: str | None
    pet_care_experience: str | None
    vetting_officer_notes: str | None
    home_inspection_scheduled_at: datetime | None
    home_inspection_notes: str | None
    adoption_agreement_url: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    dog: DogProfileResponse | None = None
    adopter: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)


class AdoptionApplicationListQueryParams(BaseModel):
    search: str | None = Field(None, description="Search by adopter name, dog name, notes")
    status: AdoptionStatus | None = None
    dog_id: uuid.UUID | None = None
    adopter_id: uuid.UUID | None = None
