"""Pydantic schemas for the Foster Management module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    @field_validator("weight_kg", mode="before")
    @classmethod
    def normalize_weight(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean == "":
                return None
            try:
                return float(v_clean)
            except ValueError:
                return None
        return v

    @field_validator("exercise_minutes", "mood_rating", mode="before")
    @classmethod
    def normalize_ints(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean == "":
                return None
            try:
                return int(v_clean)
            except ValueError:
                return None
        return v

    @field_validator("photo_urls", mode="before")
    @classmethod
    def normalize_photos(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean == "":
                return []
            return [v_clean]
        return v


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

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            return v_clean
        return v

    @field_validator("vetted_at", "inspected_at", mode="before")
    @classmethod
    def normalize_empty_datetimes(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator(
        "background_check_passed",
        "references_checked",
        "home_inspection_passed",
        "is_available",
        mode="before",
    )
    @classmethod
    def normalize_booleans(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v.strip().lower() in ("true", "1", "yes"):
                return True
            if v.strip().lower() in ("false", "0", "no"):
                return False
            if v.strip() == "":
                return None
        return v


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
    reason: str | None = Field(None, examples=["Foster period completed", "Shelter request"])


class FosterVetCheckRequest(BaseModel):
    reason: str | None = Field(None, examples=["Routine health check", "Lethargy and limping"])
    urgency: str = Field("routine", examples=["routine", "urgent", "emergency"])
    preferred_date: datetime | None = Field(None)
    notes: str | None = Field(None, examples=["Dog showing slight limp on front left paw."])

    @field_validator("urgency", mode="before")
    @classmethod
    def normalize_urgency(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            return v_clean if v_clean in ("routine", "urgent", "emergency") else "routine"
        return "routine"

    @field_validator("preferred_date", mode="before")
    @classmethod
    def normalize_preferred_date(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class FosterVetCheckResponse(BaseModel):
    placement_id: uuid.UUID
    dog_id: uuid.UUID
    foster_id: uuid.UUID
    reason: str
    urgency: str
    status: str
    requested_at: datetime
    message: str


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
