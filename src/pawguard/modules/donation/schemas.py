"""Pydantic schemas for the Donation Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse
from pawguard.modules.donation.models import DonationStatus, DonationType


class DonorProfileCreate(BaseModel):
    tax_identifier: str | None = Field(None, max_length=64)
    notes: str | None = None


class DonorProfileUpdate(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


class DonationCreate(BaseModel):
    dog_id: uuid.UUID | None = None
    amount: float = Field(..., ge=1.0)
    currency: str = Field("USD", min_length=3, max_length=3)
    donation_type: DonationType = DonationType.ONE_TIME
    notes: str | None = None


class DonationStatusUpdate(BaseModel):
    status: DonationStatus = Field(..., description="New status for the donation")


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
    payment_provider: str | None
    created_at: datetime
    dog: DogProfileResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class DonationOrderResponse(BaseModel):
    """Returned after initiating a donation - the client uses this to open the
    provider's checkout (e.g. Razorpay Checkout.js) and complete payment."""

    donation_id: uuid.UUID
    provider: str
    order_id: str
    amount: float
    currency: str
    checkout_key: str


class DonationVerifyRequest(BaseModel):
    donation_id: uuid.UUID
    gateway_order_id: str
    gateway_payment_id: str
    gateway_signature: str
