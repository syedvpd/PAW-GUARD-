"""Pydantic request and response models for companion pet APIs."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pawguard.modules.companion_pet.models import AppointmentStatus, ReminderKind


class CompanionPetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    species: str = Field("dog", min_length=1, max_length=64)
    breed: str | None = Field(None, max_length=128)
    sex: str | None = Field(None, max_length=32)
    birth_date: datetime | None = None
    color: str | None = Field(None, max_length=128)
    microchip_id: str | None = Field(None, max_length=64)
    emergency_notes: str | None = Field(None, max_length=4000)
    is_scan_enabled: bool = True
    original_dog_id: uuid.UUID | None = None
    adoption_application_id: uuid.UUID | None = None


class CompanionPetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    species: str | None = Field(None, min_length=1, max_length=64)
    breed: str | None = Field(None, max_length=128)
    sex: str | None = Field(None, max_length=32)
    birth_date: datetime | None = None
    color: str | None = Field(None, max_length=128)
    microchip_id: str | None = Field(None, max_length=64)
    emergency_notes: str | None = Field(None, max_length=4000)
    is_scan_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> "CompanionPetUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("At least one field must be provided for update.")
        return self


class CompanionPetResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    species: str
    breed: str | None
    sex: str | None
    birth_date: datetime | None
    color: str | None
    microchip_id: str | None
    emergency_notes: str | None
    is_scan_enabled: bool
    original_dog_id: uuid.UUID | None = None
    adoption_application_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MedicalRecordCreate(BaseModel):
    record_type: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    notes: str | None = Field(None, max_length=10000)
    occurred_at: datetime | None = None
    clinic_id: uuid.UUID | None = None
    stored_file_id: uuid.UUID | None = None
    next_reminder_at: datetime | None = Field(
        None,
        description=(
            "When set, a vaccination or medication reminder is automatically "
            "created for the pet owner with due_at set to this timestamp."
        ),
    )
    reminder_kind: ReminderKind | None = Field(
        None,
        description="Reminder type (vaccination or medication). Defaults to 'vaccination'.",
    )


class MedicalRecordUpdate(BaseModel):
    record_type: str | None = Field(None, min_length=1, max_length=64)
    title: str | None = Field(None, min_length=1, max_length=255)
    notes: str | None = Field(None, max_length=10000)
    occurred_at: datetime | None = None
    clinic_id: uuid.UUID | None = None
    stored_file_id: uuid.UUID | None = None


class MedicalUploadRequest(BaseModel):
    original_filename: str = Field(..., min_length=1, max_length=512)
    mime_type: str = Field(..., min_length=1, max_length=128)
    file_size: int = Field(..., gt=0)


class MedicalRecordResponse(BaseModel):
    id: uuid.UUID
    pet_id: uuid.UUID
    clinic_id: uuid.UUID | None
    authored_by_id: uuid.UUID
    stored_file_id: uuid.UUID | None
    record_type: str
    title: str
    notes: str | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SafetyTagResponse(BaseModel):
    id: uuid.UUID
    pet_id: uuid.UUID
    token_prefix: str
    is_active: bool
    last_scanned_at: datetime | None
    scan_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SafetyTagProvisionResponse(SafetyTagResponse):
    raw_token: str = Field(
        ..., description="Return value only; never persisted or returned by read endpoints."
    )


class SafetyTagScanRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=256)


class SafetyTagScanResponse(BaseModel):
    pet_id: uuid.UUID
    name: str
    species: str
    breed: str | None
    color: str | None
    emergency_notes: str | None
    photo_url: str | None = None
    status: str = Field("safe", description="Current status: safe, lost, found, reunited, or inactive.")
    lost_report_id: uuid.UUID | None = None
    lost_location: str | None = None
    lost_at: datetime | None = None
    message: str = "If this pet needs urgent care, contact a local veterinary clinic."


class VetClinicCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1, max_length=2000)
    phone: str = Field(..., min_length=3, max_length=32)
    email: str | None = Field(None, max_length=255)
    services: str | None = Field(None, max_length=4000)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    is_emergency: bool = False


class VetClinicUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = Field(None, min_length=1, max_length=2000)
    phone: str | None = Field(None, min_length=3, max_length=32)
    email: str | None = Field(None, max_length=255)
    services: str | None = Field(None, max_length=4000)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    is_emergency: bool | None = None
    is_active: bool | None = None


class VetClinicResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    phone: str
    email: str | None
    services: str | None
    latitude: float | None
    longitude: float | None
    is_emergency: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VeterinarianResponse(BaseModel):
    """A veterinarian available at a clinic for appointment booking."""

    id: uuid.UUID
    full_name: str
    email: str | None = None
    phone: str | None = None
    profile_picture_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ClinicMembershipCreate(BaseModel):
    user_id: uuid.UUID
    membership_role: str = Field("staff", min_length=1, max_length=32)


class PetAppointmentCreate(BaseModel):
    pet_id: uuid.UUID
    clinic_id: uuid.UUID
    vet_id: uuid.UUID | None = None
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(..., min_length=1, max_length=255)
    notes: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def validate_time_range(self) -> "PetAppointmentCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("Appointment end must be after appointment start.")
        return self


class PetAppointmentResponse(BaseModel):
    id: uuid.UUID
    pet_id: uuid.UUID
    owner_id: uuid.UUID
    clinic_id: uuid.UUID
    vet_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    reason: str
    notes: str | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentCancelRequest(BaseModel):
    reason: str | None = Field(None, max_length=255)


class AppointmentStatusRequest(BaseModel):
    status: Literal["confirmed", "completed", "no_show"]


class PetReminderCreate(BaseModel):
    kind: ReminderKind
    title: str = Field(..., min_length=1, max_length=255)
    details: str | None = Field(None, max_length=4000)
    due_at: datetime
    source_key: str = Field(..., min_length=1, max_length=255)


class PetReminderResponse(BaseModel):
    id: uuid.UUID
    pet_id: uuid.UUID
    owner_id: uuid.UUID
    kind: ReminderKind
    title: str
    details: str | None
    due_at: datetime
    source_key: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
