"""Pydantic schemas for the Emergency Rescue module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from pawguard.modules.rescue.models import RescueStatus


class RescueRequestCreate(BaseModel):
    reporter_name: str = Field(..., min_length=1, max_length=255)
    reporter_phone: str = Field(..., min_length=1, max_length=32)
    reporter_alternate_phone: str | None = Field(None, max_length=32)
    reporter_email: EmailStr | None = None
    is_anonymous: bool = False

    location_address: str = Field(..., min_length=1)
    location_landmark: str | None = None
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)

    animal_count: int = Field(1, ge=1)
    physical_condition: str = Field(
        ..., min_length=1, max_length=64
    )  # e.g. "Critical/Life Threatening", "Injured", etc.
    behavioral_indicators: str | None = None


class RescueRequestUpdate(BaseModel):
    status: RescueStatus | None = None
    rejection_rationale: str | None = None


class RescueDispatchCreate(BaseModel):
    assigned_driver_id: uuid.UUID | None = None
    vehicle_id: str | None = Field(None, max_length=64)
    equipment_details: str | None = None
    notes: str | None = None


class RescueDispatchResponse(BaseModel):
    id: uuid.UUID
    rescue_request_id: uuid.UUID
    assigned_driver_id: uuid.UUID | None
    vehicle_id: str | None
    equipment_details: str | None
    dispatched_at: datetime
    located_at: datetime | None
    rescued_at: datetime | None
    admitted_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None
    notes: str | None

    model_config = ConfigDict(from_attributes=True)


class RescueReportCreate(BaseModel):
    notes: str | None = None
    photos: list[str] | None = Field(None, max_length=5)


class RescueReportResponse(BaseModel):
    id: uuid.UUID
    rescue_request_id: uuid.UUID
    agent_id: uuid.UUID
    notes: str | None
    photos: list[str] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RescueRequestResponse(BaseModel):
    id: uuid.UUID
    ticket_number: str
    reporter_name: str
    reporter_phone: str
    reporter_alternate_phone: str | None
    reporter_email: str | None
    is_anonymous: bool
    location_address: str
    location_landmark: str | None
    latitude: float | None
    longitude: float | None
    animal_count: int
    physical_condition: str
    behavioral_indicators: str | None
    status: RescueStatus
    rejection_rationale: str | None
    created_at: datetime
    updated_at: datetime
    dispatch: RescueDispatchResponse | None = None
    reports: list[RescueReportResponse] = []

    model_config = ConfigDict(from_attributes=True)
