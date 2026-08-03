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
    collar_color: str | None = Field(None, max_length=64, examples=["Red"])
    collar_description: str | None = Field(None, max_length=512, examples=["Red buckle collar"])
    marker_description: str | None = Field(None, examples=["White patch on left ear"])
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
    collar_color: str | None
    collar_description: str | None
    marker_description: str | None
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
    collar_color: str | None = Field(None, max_length=64, examples=["Red"])
    collar_description: str | None = Field(None, max_length=512, examples=["Red buckle collar"])
    marker_description: str | None = Field(None, examples=["White patch on left ear"])
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
    collar_color: str | None
    collar_description: str | None
    marker_description: str | None
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
    microchip_doc_url: str | None
    vet_bill_url: str | None
    photo_proof_url: str | None
    verification_notes: str | None
    claim_submitted_at: datetime | None
    claim_reviewed_at: datetime | None
    claim_reviewed_by: uuid.UUID | None
    created_at: datetime
    # Score-basis transparency (PRR 3.10): computed by the matcher at match time
    # and attached to the match record by the service. Historical matches that
    # predate these fields fall back to these defaults.
    distance_km: float | None = None
    temporal_gap_days: float | None = None
    match_reasons: list[str] = []
    lost_report: LostReportResponse | None = None
    found_report: FoundReportResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class OwnershipClaimSubmit(BaseModel):
    """Ownership-verification claim: the claimant uploads supporting documents
    (microchip registration, vet bill, photos) and the staff reviews them."""

    microchip_doc_url: str | None = Field(
        None, max_length=512, examples=["https://example.com/microchip.pdf"]
    )
    vet_bill_url: str | None = Field(
        None, max_length=512, examples=["https://example.com/vet-bill.pdf"]
    )
    photo_proof_url: str | None = Field(
        None, max_length=512, examples=["https://example.com/owner-photo.jpg"]
    )
    verification_notes: str | None = Field(
        None, examples=["Buddy was chipped at PawHealth Clinic in 2023."]
    )


class OwnershipClaimReview(BaseModel):
    approve: bool = Field(..., examples=[True])
    verification_notes: str | None = Field(
        None, examples=["Microchip ID matches the owner registration record."]
    )
