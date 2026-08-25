"""Pydantic schemas for the Lost & Found module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pawguard.core.logging import get_logger
from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.lost_found.models import MatchStatus, ReportStatus, Species

logger = get_logger(__name__)


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
    # Permanent S3/Supabase object reference returned by
    # POST /api/v1/lost-found/photo-upload-url. Stores a stable object key (NOT a
    # presigned URL) so the backend can mint a fresh signed download URL on read.
    # Legacy externally-hosted URLs may still be supplied via ``photo_url``.
    photo_object_key: str | None = Field(
        None,
        max_length=512,
        examples=["lost-found/00000000-0000-0000-0000-000000000000.jpg"],
    )
    companion_pet_id: uuid.UUID | None = Field(None, description="Optional companion pet ID")

    @field_validator("photo_object_key")
    @classmethod
    def _validate_photo_object_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith("lost-found/"):
            raise ValueError(
                "photo_object_key must reference a lost-found upload "
                "(expected prefix 'lost-found/')."
            )
        return value


class LostFoundPhotoUploadUrlRequest(BaseModel):
    """Request metadata for a presigned S3/Supabase photo upload.

    Mirrors the Emergency (rescue) ``RescueMediaUploadUrlRequest`` contract: the
    client sends file metadata, the backend returns a presigned PUT URL and the
    permanent object key. The client uploads bytes directly to storage, then
    submits the object key on report creation.
    """

    filename: str = Field(..., examples=["buddy.jpg"])
    mime_type: str = Field(..., examples=["image/jpeg"])
    file_size: int = Field(
        ...,
        ge=1,
        le=52428800,
        description="Uploaded file size in bytes. Max 50MB.",
    )


class LostFoundPhotoUploadUrlResponse(BaseModel):
    """Presigned upload URL and permanent object key for a lost/found photo."""

    upload_url: str
    object_key: str


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
    companion_pet_id: uuid.UUID | None = None
    photo_url: str | None
    # Stable storage object key (excluded from the API response; the backend
    # resolves it to a fresh signed download URL in ``photo_url`` on every read).
    photo_object_key: str | None = Field(None, exclude=True)
    created_at: datetime
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _resolve_photo_url(self) -> "LostReportResponse":
        """Mint a fresh signed download URL from the stored object key.

        Backward compatible: legacy reports that only carry an externally
        hosted ``photo_url`` are returned unchanged.
        """
        if self.photo_object_key:
            try:
                from pawguard.services.storage_service import get_storage_service

                self.photo_url = get_storage_service().generate_public_url(
                    object_key=self.photo_object_key
                )
            except Exception:
                # Never fail report retrieval because storage signing is down;
                # fall back to any legacy URL already present.
                logger.warning(
                    "lost_report_photo_url_resolution_failed",
                    object_key=self.photo_object_key,
                    exc_info=True,
                )
        return self


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
    # Permanent S3/Supabase object reference returned by
    # POST /api/v1/lost-found/photo-upload-url. Stores a stable object key (NOT a
    # presigned URL) so the backend can mint a fresh signed download URL on read.
    # Legacy externally-hosted URLs may still be supplied via ``photo_url``.
    photo_object_key: str | None = Field(
        None,
        max_length=512,
        examples=["lost-found/00000000-0000-0000-0000-000000000000.jpg"],
    )

    @field_validator("photo_object_key")
    @classmethod
    def _validate_photo_object_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith("lost-found/"):
            raise ValueError(
                "photo_object_key must reference a lost-found upload "
                "(expected prefix 'lost-found/')."
            )
        return value


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
    # Stable storage object key (excluded from the API response; the backend
    # resolves it to a fresh signed download URL in ``photo_url`` on every read).
    photo_object_key: str | None = Field(None, exclude=True)
    created_at: datetime
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _resolve_photo_url(self) -> "FoundReportResponse":
        """Mint a fresh signed download URL from the stored object key.

        Backward compatible: legacy reports that only carry an externally
        hosted ``photo_url`` are returned unchanged.
        """
        if self.photo_object_key:
            try:
                from pawguard.services.storage_service import get_storage_service

                self.photo_url = get_storage_service().generate_public_url(
                    object_key=self.photo_object_key
                )
            except Exception:
                # Never fail report retrieval because storage signing is down;
                # fall back to any legacy URL already present.
                logger.warning(
                    "found_report_photo_url_resolution_failed",
                    object_key=self.photo_object_key,
                    exc_info=True,
                )
        return self


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


class PetSightingCreate(BaseModel):
    pet_id: uuid.UUID | None = Field(None, description="Companion pet ID or scan token target")
    lost_report_id: uuid.UUID | None = Field(None, description="Associated lost report ID if known")
    finder_name: str = Field(..., min_length=1, max_length=255, examples=["Jane Doe"])
    finder_phone: str = Field(..., min_length=3, max_length=32, examples=["+15551234567"])
    finder_address: str | None = Field(None, max_length=1000)
    latitude: float | None = Field(None, ge=-90.0, le=90.0, examples=[17.4326])
    longitude: float | None = Field(None, ge=-180.0, le=180.0, examples=[78.4071])
    location_address: str = Field(
        ..., min_length=1, max_length=1000, examples=["Corner of 5th Ave and Main St"]
    )
    message: str | None = Field(
        None, max_length=4000, examples=["Pet is safe with me, call me ASAP!"]
    )


class PetSightingResponse(BaseModel):
    id: uuid.UUID
    pet_id: uuid.UUID | None
    lost_report_id: uuid.UUID | None
    finder_name: str
    finder_phone: str
    finder_address: str | None
    latitude: float | None
    longitude: float | None
    location_address: str
    message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnifiedReportResponse(BaseModel):
    """Unified lookup wrapper for a lost or found report resolved by id.

    ``kind`` discriminates the resolved report type; ``report`` carries the
    typed response. Reuses the existing per-type responses so PII masking
    (applied in the router) and photo-URL resolution stay identical to the
    per-type endpoints.
    """

    kind: str = Field(..., description="Resolved report type: 'lost' or 'found'")
    report: LostReportResponse | FoundReportResponse

    model_config = ConfigDict(from_attributes=True)
