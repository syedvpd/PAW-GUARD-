"""Pydantic schemas for the Dog Management module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pawguard.modules.dog.models import (
    DogActivityEventType,
    DogBreedClassification,
    DogEarShape,
    DogGender,
    DogStatus,
    DogTailType,
    DogTemperament,
)

_shared_storage_service: Any = None


class DogProfileCreate(BaseModel):
    rescue_case_id: uuid.UUID | None = None
    microchip_id: str | None = Field(
        None,
        max_length=64,
        description=(
            "Optional 15-digit chip number. When omitted, PawGuard auto-generates "
            "a unique value at registration."
        ),
    )

    name: str = Field(..., min_length=1, max_length=255, examples=["Barnaby"])
    breed: str = Field("indie_mix", max_length=128, examples=["Indie Mix"])
    breed_classification: DogBreedClassification | None = Field(
        None, description="Pure/Mix/Unknown; inferred from breed when omitted."
    )
    status: DogStatus | None = None
    gender: DogGender = DogGender.UNKNOWN
    is_spayed_neutered: bool = False
    estimated_age: str | None = Field(None, max_length=64, examples=["2 years"])
    age_months: int | None = Field(
        None, ge=0, le=600, description="Derived from estimated_age when omitted."
    )
    weight: float | None = Field(None, ge=0.0, examples=[16.4])
    color: str | None = Field(None, max_length=64, examples=["Tan/White"])
    temperament: DogTemperament | None = Field(None, examples=["friendly"])
    ear_shape: DogEarShape | None = Field(None, examples=["floppy"])
    tail_type: DogTailType | None = Field(None, examples=["curled"])
    distinctive_markers: str | None = Field(
        None, max_length=512, examples=["White patch on chest, notched left ear"]
    )
    shelter_facility_id: uuid.UUID | None = None
    section_id: uuid.UUID | None = None
    kennel_id: uuid.UUID | None = None
    foster_home_id: uuid.UUID | None = None
    is_adoptable: bool = False
    is_quarantine_passed: bool = False
    image_urls: list[str] = Field(default_factory=list)
    photo_url: str | None = None
    intake_condition: str | None = None
    medical_notes: str | None = None
    rescue_date: datetime | str | None = None
    rescue_location: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_intake_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Aliases for common frontend form fields
            if not data.get("name"):
                data["name"] = (
                    data.get("dog_name") or data.get("code_name") or data.get("shelter_name")
                )
            if not data.get("rescue_case_id"):
                data["rescue_case_id"] = data.get("rescue_id") or data.get("case_id")
            if not data.get("gender") and data.get("sex"):
                data["gender"] = data.get("sex")
            if not data.get("distinctive_markers"):
                data["distinctive_markers"] = data.get("identification_marks") or data.get(
                    "markers"
                )

            # 2. Coerce empty strings to None for UUID and optional string fields
            for uuid_field in (
                "rescue_case_id",
                "shelter_facility_id",
                "section_id",
                "kennel_id",
                "foster_home_id",
                "microchip_id",
                "breed_classification",
                "temperament",
                "ear_shape",
                "tail_type",
                "color",
                "distinctive_markers",
            ):
                if data.get(uuid_field) == "":
                    data[uuid_field] = None

            # 3. Case-insensitive normalization for controlled enums
            if isinstance(data.get("gender"), str):
                g_str = data["gender"].strip().lower()
                for g in DogGender:
                    if g.value == g_str:
                        data["gender"] = g
                        break
            if isinstance(data.get("status"), str):
                s_str = data["status"].strip().lower()
                for s in DogStatus:
                    if s.value == s_str:
                        data["status"] = s
                        break
            if isinstance(data.get("breed_classification"), str):
                b_str = data["breed_classification"].strip().lower()
                for b in DogBreedClassification:
                    if b.value == b_str:
                        data["breed_classification"] = b
                        break
            if isinstance(data.get("temperament"), str):
                t_str = data["temperament"].strip().lower()
                for t in DogTemperament:
                    if t.value == t_str:
                        data["temperament"] = t
                        break
            if isinstance(data.get("ear_shape"), str):
                e_str = data["ear_shape"].strip().lower()
                for e in DogEarShape:
                    if e.value == e_str:
                        data["ear_shape"] = e
                        break
            if isinstance(data.get("tail_type"), str):
                tt_str = data["tail_type"].strip().lower()
                for tt in DogTailType:
                    if tt.value == tt_str:
                        data["tail_type"] = tt
                        break

            # 4. Handle photos and image URLs
            photo = data.get("photo_url") or data.get("image_url")
            raw_urls = data.get("image_urls") or data.get("photo_gallery_urls") or []
            if isinstance(raw_urls, str):
                raw_urls = [raw_urls]
            elif not isinstance(raw_urls, list):
                raw_urls = []
            urls = [str(u).strip() for u in raw_urls if u]
            if photo and str(photo).strip() not in urls:
                urls.append(str(photo).strip())
            data["image_urls"] = urls

            # 5. Age string normalization
            if data.get("estimated_age") is not None and not isinstance(
                data.get("estimated_age"), str
            ):
                data["estimated_age"] = str(data["estimated_age"])
        return data

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Barnaby",
                "breed": "Indie Mix",
                "breed_classification": "pure",
                "gender": "male",
                "is_spayed_neutered": False,
                "estimated_age": "2 years",
                "age_months": 24,
                "weight": 16.4,
                "color": "Tan/White",
                "temperament": "friendly",
                "ear_shape": "floppy",
                "tail_type": "curled",
                "distinctive_markers": "White patch on chest, notched left ear",
                "is_adoptable": False,
                "is_quarantine_passed": False,
            }
        }
    )


class DogProfileUpdate(BaseModel):
    microchip_id: str | None = Field(None, examples=["985141002345678"])
    name: str | None = Field(None, examples=["Barnaby"])
    breed: str | None = Field(None, examples=["Indie Mix"])
    breed_classification: DogBreedClassification | None = Field(
        None, description="Pure/Mix/Unknown; re-inferred when breed changes."
    )
    gender: DogGender | None = Field(None, examples=["male"])
    is_spayed_neutered: bool | None = Field(None, examples=[True])
    estimated_age: str | None = Field(None, examples=["2 years"])
    age_months: int | None = Field(
        None, ge=0, le=600, description="Re-derived from estimated_age when null."
    )
    weight: float | None = Field(None, examples=[16.4])
    color: str | None = Field(None, examples=["Tan/White"])
    temperament: DogTemperament | None = Field(None, examples=["friendly"])
    ear_shape: DogEarShape | None = Field(None, examples=["floppy"])
    tail_type: DogTailType | None = Field(None, examples=["curled"])
    distinctive_markers: str | None = Field(None, max_length=512, examples=["White patch on chest"])
    status: DogStatus | None = Field(None, examples=["shelter"])
    shelter_facility_id: uuid.UUID | None = None
    section_id: uuid.UUID | None = None
    kennel_id: uuid.UUID | None = None
    foster_home_id: uuid.UUID | None = None
    is_adoptable: bool | None = Field(None, examples=[False])
    is_quarantine_passed: bool | None = Field(None, examples=[True])
    image_urls: list[str] | None = None
    photo_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _sanitize_update_images(cls, data: Any) -> Any:
        if isinstance(data, dict):
            photo = data.get("photo_url") or data.get("image_url")
            raw_urls = data.get("image_urls") or data.get("photo_gallery_urls")
            if raw_urls is not None:
                if isinstance(raw_urls, str):
                    raw_urls = [raw_urls]
                elif not isinstance(raw_urls, list):
                    raw_urls = []
                urls = [str(u).strip() for u in raw_urls if u]
                if photo and str(photo).strip() not in urls:
                    urls.append(str(photo).strip())
                data["image_urls"] = urls
            elif photo:
                data["image_urls"] = [str(photo).strip()]
        return data


class DogStatusUpdate(BaseModel):
    status: DogStatus = Field(..., description="New status for the dog", examples=["shelter"])


class DogAdoptabilityUpdate(BaseModel):
    is_adoptable: bool = Field(..., description="Whether dog is cleared and available for adoption")
    is_quarantine_passed: bool | None = Field(None, description="Whether dog passed quarantine")


class DogProfileResponse(BaseModel):
    id: uuid.UUID
    registration_number: str
    rescue_case_id: uuid.UUID | None
    microchip_id: str | None
    version_id: int = Field(default=1, description="Version counter for optimistic locking")

    @field_validator("version_id", mode="before")
    @classmethod
    def _coerce_version_id(cls, v: Any) -> int:
        if v is None:
            return 1
        return int(v)

    name: str
    breed: str
    breed_classification: DogBreedClassification
    gender: DogGender
    is_spayed_neutered: bool
    estimated_age: str | None
    age_months: int | None
    weight: float | None
    color: str | None
    temperament: DogTemperament | None
    ear_shape: DogEarShape | None
    tail_type: DogTailType | None
    distinctive_markers: str | None
    status: DogStatus
    shelter_facility_id: uuid.UUID | None
    section_id: uuid.UUID | None
    kennel_id: uuid.UUID | None
    foster_home_id: uuid.UUID | None
    is_adoptable: bool
    is_quarantine_passed: bool
    image_urls: list[str] = Field(default_factory=list)
    photo_gallery_urls: list[str] = Field(default_factory=list)
    photo_url: str | None = None
    image_url: str | None = None
    photo_variants: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("image_urls", mode="before")
    @classmethod
    def _coerce_image_urls(cls, v: Any) -> list[str]:
        """ORM column may be NULL; coerce to empty list for the response."""
        if v is None:
            return []
        if isinstance(v, list):
            return [str(u) for u in v if u]
        return []

    @model_validator(mode="after")
    def _sync_photo_fields(self) -> "DogProfileResponse":
        """Expose image_urls under photo_gallery_urls, photo_url, and image_url
        so all field names are available for different web and mobile consumers,
        and dynamically convert raw S3 keys to fresh presigned download URLs."""
        resolved = []
        variants_map: dict[str, str] = {}
        if self.image_urls:
            from pawguard.services.storage_service import StorageService

            global _shared_storage_service
            if "_shared_storage_service" not in globals() or _shared_storage_service is None:
                _shared_storage_service = StorageService()
            s3 = _shared_storage_service
            for u in self.image_urls:
                try:
                    fresh = s3.sign_media_url(u, prefer_public=True)
                    resolved.append(fresh or u)
                except Exception:
                    resolved.append(u)
            if self.image_urls:
                variants_map = s3.get_responsive_variants(self.image_urls[0])

        self.image_urls = resolved
        self.photo_gallery_urls = resolved
        self.photo_variants = variants_map
        first = resolved[0] if resolved else None
        if not self.photo_url:
            self.photo_url = first
        if not self.image_url:
            self.image_url = first
        return self

    model_config = ConfigDict(from_attributes=True)


class PublicDogScanResponse(BaseModel):
    """Privacy-safe dog status exposed by the public QR scan endpoint."""

    name: str
    breed: str
    breed_classification: DogBreedClassification
    estimated_age: str | None
    gender: DogGender
    weight_kg: float | None
    temperament: DogTemperament | None
    color: str | None
    photo_gallery_urls: list[str] = Field(default_factory=list)
    current_status: DogStatus
    is_adoptable: bool
    registration_number: str
    adopter_name: str | None = None
    adopter_phone: str | None = None
    adopter_email: str | None = None


class DogListQueryParams(BaseModel):
    """Public adoption-directory filters (PRR 3.1.4: age, size, temperaments,
    location) plus staff-facing registry filters."""

    search: str | None = Field(None, description="Search by name, breed, registration number")
    status: DogStatus | None = None
    is_adoptable: bool | None = None
    breed: str | None = None
    breed_classification: DogBreedClassification | None = None
    gender: DogGender | None = None
    temperament: DogTemperament | None = None
    min_age_months: int | None = Field(None, ge=0, description="Minimum age in months")
    max_age_months: int | None = Field(None, ge=0, description="Maximum age in months")
    min_weight: float | None = Field(None, ge=0.0, description="Minimum weight in kg")
    max_weight: float | None = Field(None, ge=0.0, description="Maximum weight in kg")
    location: str | None = Field(
        None, description="Free-text match on the shelter facility name/address"
    )


class DogWeightLogCreate(BaseModel):
    """One weight measurement for a dog (PRR 3.4 Weight History)."""

    weight: float = Field(..., gt=0, le=2000, description="Weight in kg", examples=[16.4])
    measured_at: datetime | None = Field(None, description="Defaults to now when omitted.")
    notes: str | None = Field(None, max_length=512, examples=["Post-surgery weigh-in"])


class DogWeightLogResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    measured_by: uuid.UUID | None
    weight: float
    measured_at: datetime
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DogActivityLogResponse(BaseModel):
    """One immutable entry in a dog's lifecycle activity stream (PRR 3.4)."""

    id: uuid.UUID
    dog_id: uuid.UUID
    actor_id: uuid.UUID | None
    event_type: DogActivityEventType
    message: str
    event_metadata: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DogSafetyTagResponse(BaseModel):
    """Public/Admin view of a Dog Master's Safety Tag."""

    id: uuid.UUID
    dog_id: uuid.UUID
    pet_id: uuid.UUID | None = None
    token_prefix: str
    is_active: bool
    last_scanned_at: datetime | None = None
    scan_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DogSafetyTagProvisionResponse(DogSafetyTagResponse):
    """Response when a Safety Tag is provisioned; exposes raw_token ONLY once."""

    raw_token: str


class DogSafetyTagResolveRequest(BaseModel):
    """Request payload for authoritative Safety Tag token resolution."""

    raw_token: str = Field(..., min_length=1, description="Complete raw Safety Tag token string")


class DogSafetyTagResolveResponse(BaseModel):
    """Authoritative E2E response mapping raw_token -> Safety Tag -> Dog Master."""

    tag_id: uuid.UUID
    dog_id: uuid.UUID
    token_prefix: str
    is_active: bool
    last_scanned_at: datetime | None = None
    scan_count: int = 0
    dog: DogProfileResponse
