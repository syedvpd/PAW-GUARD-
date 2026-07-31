"""Pydantic schemas for the Adoption Management module."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.adoption.models import AdoptionStatus
from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse


class AdoptionApplicationCreate(BaseModel):
    dog_id: uuid.UUID
    residential_status: str = Field(
        ..., min_length=3, max_length=32, examples=["owned"]
    )  # owned, rented
    has_landlord_approval: bool = False
    has_yard_fence: bool = False
    household_members_count: int = Field(1, ge=1, examples=[3])
    existing_pets_medical_details: str | None = Field(
        None, examples=["One neutered male cat, up to date on vaccinations."]
    )
    pet_care_experience: str | None = Field(
        None, examples=["Owned a Labrador for 10 years prior to this application."]
    )


class AdoptionApplicationUpdate(BaseModel):
    status: AdoptionStatus | None = Field(None, examples=["home_check"])
    vetting_officer_notes: str | None = Field(
        None, examples=["Phone interview completed, applicant is a strong candidate."]
    )
    home_inspection_scheduled_at: datetime | None = Field(
        None, examples=["2026-08-15T14:00:00Z"]
    )
    home_inspection_notes: str | None = Field(
        None, examples=["Yard is securely fenced, home is clean and pet-ready."]
    )
    adoption_agreement_url: str | None = Field(
        None, examples=["documents/agreement_1a2b3c.pdf"]
    )


class AdoptionStatusUpdate(BaseModel):
    status: AdoptionStatus = Field(
        ..., description="New status for the adoption application", examples=["approved"]
    )


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


class AdoptionScoreCreate(BaseModel):
    home_environment_score: int = Field(..., ge=1, le=10, examples=[8])
    pet_care_knowledge_score: int = Field(..., ge=1, le=10, examples=[7])
    financial_readiness_score: int = Field(..., ge=1, le=10, examples=[9])
    lifestyle_compatibility_score: int = Field(..., ge=1, le=10, examples=[8])
    recommendation: str = Field(..., min_length=1, max_length=32, examples=["approve"])
    notes: str | None = Field(
        None, examples=["Strong candidate, active lifestyle matches dog's energy."]
    )


class AdoptionScoreResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    scored_by_id: uuid.UUID
    home_environment_score: int
    pet_care_knowledge_score: int
    financial_readiness_score: int
    lifestyle_compatibility_score: int
    overall_score: Decimal
    recommendation: str
    notes: str | None
    scored_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdoptionApplicationDetail(AdoptionApplicationResponse):
    scores: list[AdoptionScoreResponse] = []


class AdoptionApplicationListQueryParams(BaseModel):
    search: str | None = Field(None, description="Search by adopter name, dog name, notes")
    status: AdoptionStatus | None = None
    dog_id: uuid.UUID | None = None
    adopter_id: uuid.UUID | None = None
