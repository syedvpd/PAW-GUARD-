"""Pydantic schemas for the Invoicing & Service Fee Collection module."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from pawguard.modules.invoice.models import InvoiceStatus, InvoiceType


class InvoiceCreate(BaseModel):
    invoice_type: InvoiceType = Field(
        ...,
        description="Type of invoice: partner_billing or service_fee",
        examples=["partner_billing"],
    )
    amount: Decimal = Field(
        ..., gt=Decimal("0.00"), description="Invoice amount", examples=[1500.00]
    )
    currency: str = Field("INR", min_length=3, max_length=3, examples=["INR"])
    description: str = Field(
        ...,
        min_length=1,
        description="Line item description",
        examples=["Platform commission for July 2026"],
    )
    due_date: date | None = Field(None, description="Payment due date", examples=["2026-08-15"])

    # Who's being billed — at least one of billed_org_name or billed_user_id should be provided
    billed_org_name: str | None = Field(None, max_length=255, examples=["City Veterinary Clinic"])
    billed_user_id: uuid.UUID | None = Field(
        None, examples=["00000000-0000-0000-0000-000000000000"]
    )
    recipient_email: EmailStr | None = Field(None, examples=["billing@cityvet.com"])
    recipient_phone: str | None = Field(None, max_length=32, examples=["+91-9876543210"])

    # Linkage to originating domain
    source_module: str | None = Field(None, max_length=64, examples=["companion_pets.appointment"])
    source_reference_id: uuid.UUID | None = Field(
        None, examples=["00000000-0000-0000-0000-000000000000"]
    )

    @model_validator(mode="before")
    @classmethod
    def _pre_normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if d.get("recipient_email") == "":
                d["recipient_email"] = None
            if d.get("recipient_phone") == "":
                d["recipient_phone"] = None
            return d
        return data

    @model_validator(mode="after")
    def _validate_billing_target(self) -> "InvoiceCreate":
        if (
            not self.billed_org_name
            and not self.billed_user_id
            and not self.recipient_email
            and not self.recipient_phone
        ):
            raise ValueError(
                "At least one recipient identifier (billed_org_name, billed_user_id, recipient_email, or recipient_phone) must be provided."
            )
        return self


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    invoice_number: str
    invoice_type: InvoiceType
    status: InvoiceStatus
    billed_org_name: str | None = None
    billed_user_id: uuid.UUID | None = None
    recipient_email: str | None = None
    recipient_phone: str | None = None
    amount: Decimal
    currency: str
    description: str
    due_date: date | None = None
    source_module: str | None = None
    source_reference_id: uuid.UUID | None = None
    payment_provider: str | None = None
    payment_link_id: str | None = None
    payment_link_url: str | None = None
    paid_at: datetime | None = None
    cancellation_reason: str | None = None
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceCancelRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        examples=["Client requested cancellation; billed in error."],
    )


class InvoiceStatusUpdate(BaseModel):
    status: InvoiceStatus = Field(..., description="Target status (e.g. paid, failed)")
    notes: str | None = Field(
        None, max_length=500, description="Reason / audit notes for manual status update"
    )
    paid_at: datetime | None = Field(
        None, description="Offline payment timestamp if marking as paid"
    )
