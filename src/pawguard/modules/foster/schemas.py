"""Pydantic schemas for the Foster Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse
from pawguard.modules.foster.models import FosterStatus


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

