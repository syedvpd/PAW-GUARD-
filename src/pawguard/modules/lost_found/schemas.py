"""Pydantic schemas for the Lost & Found module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.lost_found.models import MatchStatus, ReportStatus, Species


class LostReportCreate(BaseModel):
    species: Species = Field(Species.DOG)
    pet_name: str = Field(..., min_length=1, max_length=255, examples=["Buddy"])
    breed: str = Field(..., min_length=1, max_length=128, examples=["Beagle Mix"])
    color: str = Field(..., min_length=1, max_length=64, examples=["Tan/White"])
    microchip_id: str | None = Field(None, max_length=64, examples=["985141002345678"])
    location_address: str = Field(..., min_length=1, examples=["Jubilee Hills Sector 2"])
    latitude: float | None = Field(None, ge=-90.0, le=90.0, examples=[17.4326])
    longitude: float | None = Field(None, ge=-180.0, le=180.0, examples=[78.4071])
    lost_at: datetime = Field(..., examples=["2026-07-25T14:30:00Z"])
    photo_url: str | None = Field(None, max_length=512, examples=["https://example.com/buddy.jpg"])


class LostReportResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    species: Species
    pet_name: str
    breed: str
    color: str
    microchip_id: str | None
    location_address: str
    latitude: float | None
    longitude: float | None
    lost_at: datetime
    status: ReportStatus
    photo_url: str | None
    created_at: datetime
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)


class FoundReportCreate(BaseModel):
    species: Species = Field(Species.DOG)
    breed_observed: str = Field(..., min_length=1, max_length=128, examples=["Beagle Mix"])
    color_observed: str = Field(..., min_length=1, max_length=64, examples=["Tan/White"])
    location_address: str = Field(..., min_length=1, examples=["Jubilee Hills Sector 3"])
    latitude: float | None = Field(None, ge=-90.0, le=90.0, examples=[17.4321])
    longitude: float | None = Field(None, ge=-180.0, le=180.0, examples=[78.4055])
    found_at: datetime = Field(..., examples=["2026-07-26T09:15:00Z"])
    photo_url: str | None = Field(None, max_length=512, examples=["https://example.com/found.jpg"])


class FoundReportResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    species: Species
    breed_observed: str
    color_observed: str
    location_address: str
    latitude: float | None
    longitude: float | None
    found_at: datetime
    status: ReportStatus
    photo_url: str | None
    created_at: datetime
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)


class ReportMatchResponse(BaseModel):
    id: uuid.UUID
    lost_report_id: uuid.UUID
    found_report_id: uuid.UUID
    confidence_score: float
    status: MatchStatus
    created_at: datetime
    lost_report: LostReportResponse | None = None
    found_report: FoundReportResponse | None = None

    model_config = ConfigDict(from_attributes=True)
