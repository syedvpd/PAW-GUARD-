"""Pydantic schemas for the Donation Management module."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.core.config import get_settings
from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse
from pawguard.modules.donation.models import (
    CampaignStatus,
    CampaignType,
    DonationStatus,
    DonationType,
    SponsorshipStatus,
)


def _default_currency() -> str:
    return get_settings().payment_currency


class DonorProfileCreate(BaseModel):
    tax_identifier: str | None = Field(None, max_length=64, examples=["ABCDE1234F"])
    notes: str | None = Field(None, examples=["Prefers monthly recurring donations."])


class DonorProfileUpdate(BaseModel):
    tax_identifier: str | None = Field(None, max_length=64, examples=["ABCDE1234F"])
    notes: str | None = Field(None, examples=["Updated preference: quarterly giving."])


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
    campaign_id: uuid.UUID | None = Field(
        None, description="Attach this donation to a fundraising campaign."
    )
    amount: float = Field(..., ge=1.0, examples=[50.0])
    currency: str = Field(
        default_factory=_default_currency, min_length=3, max_length=3, examples=["USD"]
    )
    donation_type: DonationType = DonationType.ONE_TIME
    notes: str | None = Field(None, examples=["In memory of Rex."])


class DonationStatusUpdate(BaseModel):
    status: DonationStatus = Field(
        ..., description="New status for the donation", examples=["success"]
    )


class DonationResponse(BaseModel):
    id: uuid.UUID
    donor_id: uuid.UUID
    dog_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    amount: float
    currency: str
    donation_type: DonationType
    status: DonationStatus
    transaction_id: str | None
    notes: str | None
    payment_provider: str | None
    receipt_file_key: str | None
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
    gateway_order_id: str = Field(..., examples=["order_NqXJz9k8bYQm2c"])
    gateway_payment_id: str = Field(..., examples=["pay_NqXK1a7fRZ3wLp"])
    gateway_signature: str = Field(..., examples=["9f8c3e1a2b4d5e6f7a8b9c0d1e2f3a4b"])


class SponsorshipCreate(BaseModel):
    dog_id: uuid.UUID
    monthly_amount: float = Field(..., ge=1.0, examples=[25.0])
    currency: str = Field(
        default_factory=_default_currency, min_length=3, max_length=3, examples=["USD"]
    )


class SponsorshipStatusUpdate(BaseModel):
    status: SponsorshipStatus = Field(..., examples=["paused"])


class SponsorshipResponse(BaseModel):
    id: uuid.UUID
    donor_id: uuid.UUID
    dog_id: uuid.UUID
    monthly_amount: float
    currency: str
    status: SponsorshipStatus
    next_charge_date: date
    started_at: datetime
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    dog: DogProfileResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class DonationCampaignCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=128, examples=["Rescue the Pack"])
    description: str | None = Field(None, examples=["Funds emergency rescue equipment."])
    target_amount: float = Field(..., ge=1.0, examples=[5000.0])
    currency: str = Field(
        default_factory=_default_currency, min_length=3, max_length=3, examples=["USD"]
    )
    campaign_type: CampaignType = CampaignType.GENERAL
    status: CampaignStatus = CampaignStatus.DRAFT
    start_date: date = Field(..., examples=["2026-08-01"])
    end_date: date | None = Field(None, examples=["2026-09-30"])


class DonationCampaignUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=128)
    description: str | None = None
    target_amount: float | None = Field(None, ge=1.0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    campaign_type: CampaignType | None = None
    status: CampaignStatus | None = None
    start_date: date | None = None
    end_date: date | None = None


class DonationCampaignResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    target_amount: float
    currency: str
    campaign_type: CampaignType
    status: CampaignStatus
    start_date: date
    end_date: date | None
    raised_amount: float
    donor_count: int
    progress_percentage: float
    goal_reached_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
