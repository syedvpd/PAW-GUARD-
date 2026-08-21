"""Pydantic schemas for the Foster Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse
from pawguard.modules.foster.models import (
    FosterPlacementStatus,
    FosterStatus,
    SupplyItemType,
)


class FosterProgressLogCreate(BaseModel):
    weight_kg: float | None = Field(None, ge=0, le=999.99, examples=[16.4])
    behavior_notes: str | None = Field(
        None, examples=["Playful and settled well, no anxiety signs."]
    )
    feeding_notes: str | None = Field(None, examples=["Ate full portion, no leftovers."])
    medication_notes: str | None = Field(
        None, examples=["Gave morning antibiotic dose on schedule."]
    )
    exercise_minutes: int | None = Field(None, ge=0, examples=[30])
    photo_urls: list[str] | None = Field(None, examples=[["https://example.com/foster/day1.jpg"]])
    mood_rating: int | None = Field(None, ge=1, le=5, examples=[4])
    notes: str | None = Field(None, examples=["Doing great overall."])


class FosterProgressLogResponse(BaseModel):
    id: uuid.UUID
    placement_id: uuid.UUID
    tracked_by_id: uuid.UUID
    weight_kg: float | None
    behavior_notes: str | None
    feeding_notes: str | None
    medication_notes: str | None
    exercise_minutes: int | None
    photo_urls: list[str] | None
    mood_rating: int | None
    notes: str | None
    logged_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FosterProfileCreate(BaseModel):
    preferences: str | None = Field(None, examples=["Puppies, Medical Recovery"])
    max_capacity: int = Field(1, ge=1, examples=[2])
    notes: str | None = Field(None, examples=["Fenced backyard, prior fostering experience."])


class FosterProfileUpdate(BaseModel):
    status: FosterStatus | None = Field(None, examples=["approved"])
    preferences: str | None = Field(None, examples=["Senior Dogs"])
    max_capacity: int | None = Field(None, examples=[2])
    is_available: bool | None = Field(None, examples=[True])
    notes: str | None = Field(None, examples=["Home inspection passed on 2026-07-20."])

    # Vetting & Background Verification
    background_check_passed: bool | None = Field(None, examples=[True])
    background_check_notes: str | None = Field(None, examples=["Background check clear."])
    references_checked: bool | None = Field(None, examples=[True])
    reference_notes: str | None = Field(None, examples=["References verified."])
    vetting_notes: str | None = Field(None, examples=["Background check clear."])
    vetted_at: datetime | None = Field(None)

    # Home Inspection
    home_inspection_passed: bool | None = Field(None, examples=[True])
    home_inspection_notes: str | None = Field(None, examples=["Fenced yard verified."])
    home_inspection_address: str | None = Field(None, examples=["123 Shelter Way"])
    inspected_at: datetime | None = Field(None)


class FosterProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: FosterStatus
    preferences: str | None
    max_capacity: int
    active_count: int
    is_available: bool
    notes: str | None

    # Vetting & Background Verification
    background_check_passed: bool | None = None
    background_check_notes: str | None = None
    references_checked: bool | None = None
    reference_notes: str | None = None
    vetting_notes: str | None = None
    vetted_at: datetime | None = None

    # Home Inspection
    home_inspection_passed: bool | None = None
    home_inspection_notes: str | None = None
    home_inspection_address: str | None = None
    inspected_at: datetime | None = None

    created_at: datetime
    updated_at: datetime
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)


class FosterPlacementCreate(BaseModel):
    dog_id: uuid.UUID
    notes: str | None = Field(None, examples=["Placing for post-surgery recovery, 4-6 weeks."])


class FosterPlacementResponse(BaseModel):
    id: uuid.UUID
    foster_id: uuid.UUID
    dog_id: uuid.UUID
    placed_at: datetime
    returned_at: datetime | None
    is_active: bool
    status: FosterPlacementStatus
    adoption_application_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    dog: DogProfileResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class FosterReturnRequest(BaseModel):
    notes: str | None = Field(None, examples=["Fully recovered, ready to return to shelter."])


class FosterSupplyDispatchCreate(BaseModel):
    item_type: SupplyItemType
    description: str | None = Field(None, examples=["20lb bag of puppy food"])
    quantity: int = Field(1, ge=1, examples=[1])


class FosterSupplyDispatchResponse(BaseModel):
    id: uuid.UUID
    placement_id: uuid.UUID
    dispatched_by_id: uuid.UUID
    item_type: SupplyItemType
    description: str | None
    quantity: int
    dispatched_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

