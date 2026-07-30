"""Pydantic schemas for the Foster Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse
from pawguard.modules.foster.models import FosterStatus


class FosterProgressLogCreate(BaseModel):
    weight_kg: float | None = Field(None, ge=0, le=999.99)
    behavior_notes: str | None = None
    feeding_notes: str | None = None
    medication_notes: str | None = None
    exercise_minutes: int | None = Field(None, ge=0)
    photo_urls: list[str] | None = None
    mood_rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = None


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
    preferences: str | None = None
    max_capacity: int = Field(1, ge=1)
    notes: str | None = None


class FosterProfileUpdate(BaseModel):
    status: FosterStatus | None = None
    preferences: str | None = None
    max_capacity: int | None = None
    is_available: bool | None = None
    notes: str | None = None


class FosterProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: FosterStatus
    preferences: str | None
    max_capacity: int
    active_count: int
    is_available: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)


class FosterPlacementCreate(BaseModel):
    dog_id: uuid.UUID
    notes: str | None = None


class FosterPlacementResponse(BaseModel):
    id: uuid.UUID
    foster_id: uuid.UUID
    dog_id: uuid.UUID
    placed_at: datetime
    returned_at: datetime | None
    is_active: bool
    notes: str | None
    created_at: datetime
    dog: DogProfileResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class FosterReturnRequest(BaseModel):
    notes: str | None = None

