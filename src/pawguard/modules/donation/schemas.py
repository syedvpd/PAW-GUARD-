"""Pydantic schemas for the Donation Management module."""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse
from pawguard.modules.donation.models import DonationStatus, DonationType


class DonorProfileCreate(BaseModel):
    tax_identifier: str | None = Field(None, max_length=64)
    notes: str | None = None


class DonorProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    tax_identifier: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    user: UserProfile | None = None

    class Config:
        from_attributes = True


class DonationCreate(BaseModel):
    dog_id: uuid.UUID | None = None
    amount: float = Field(..., ge=1.0)
    currency: str = Field("USD", min_length=3, max_length=3)
    donation_type: DonationType = DonationType.ONE_TIME
    notes: str | None = None


class DonationResponse(BaseModel):
    id: uuid.UUID
    donor_id: uuid.UUID
    dog_id: uuid.UUID | None
    amount: float
    currency: str
    donation_type: DonationType
    status: DonationStatus
    transaction_id: str | None
    notes: str | None
    created_at: datetime
    dog: DogProfileResponse | None = None

    class Config:
        from_attributes = True
