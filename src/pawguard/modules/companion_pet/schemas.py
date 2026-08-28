"""Pydantic request and response models for companion pet APIs."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

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
    title: str | None = Field(None, max_length=255)
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

    @model_validator(mode="before")
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "description" in data and data["description"]:
                if "title" not in data or not data["title"]:
                    data["title"] = data["description"]
                if "notes" not in data or not data["notes"]:
                    data["notes"] = data["description"]
            if "date" in data and data["date"]:
                if "occurred_at" not in data or not data["occurred_at"]:
                    from datetime import datetime

                    val = data["date"]
                    if isinstance(val, str):
                        try:
                            if len(val) == 10:
                                dt = datetime.fromisoformat(f"{val}T00:00:00+00:00")
                            else:
                                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                        except ValueError:
                            dt = None
                    else:
                        dt = val
                    if dt:
                        data["occurred_at"] = dt
        return data

    @model_validator(mode="after")
    def validate_required_title(self) -> "MedicalRecordCreate":
        if not self.title:
            raise ValueError("title (or description) is required")
        return self


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

    @computed_field
    @property
    def description(self) -> str:
        return self.title

    @computed_field
    @property
    def date(self) -> datetime:
        return self.occurred_at


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
    token: str | None = Field(None, max_length=256)

    @model_validator(mode="before")
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and "tag_code" in data and data["tag_code"]:
            if "token" not in data or not data["token"]:
                data["token"] = data["tag_code"]
        return data

    @model_validator(mode="after")
    def validate_required_token(self) -> "SafetyTagScanRequest":
        if not self.token:
            raise ValueError("token (or tag_code) is required")
        return self


class SafetyTagScanResponse(BaseModel):
    id: uuid.UUID | None = None
    dog_id: uuid.UUID | None = None
    pet_id: uuid.UUID | None = None
    token_prefix: str | None = None
    is_active: bool = True
    last_scanned_at: datetime | None = None
    scan_count: int = 0

    # Resolved Animal Master Attributes
    name: str
    species: str = "dog"
    breed: str | None = None
    color: str | None = None
    gender: str | None = None
    microchip_id: str | None = None
    emergency_notes: str | None = None
    photo_url: str | None = None

    # Dynamic Lifecycle State ("shelter", "fostered", "clinic", "adopted", "rescued", "safe", "lost", etc.)
    status: str = Field("safe", description="Current dynamic status of the animal.")

    # Lost & Found Banner
    is_lost: bool = False
    lost_report_id: uuid.UUID | None = None
    lost_location: str | None = None
    lost_at: datetime | None = None

    # Public-Safe Contact Details (Masked PII)
    owner_name: str | None = None
    owner_phone: str | None = None
    foster_name: str | None = None
    foster_phone: str | None = None
    facility_name: str | None = None
    facility_phone: str | None = None

    message: str = "If this animal needs urgent care, contact PawGuard emergency rescue or a local veterinary clinic."


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
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reason: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=4000)

    @model_validator(mode="before")
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "scheduled_at" in data and data["scheduled_at"]:
                from datetime import datetime, timedelta

                val = data["scheduled_at"]
                if isinstance(val, str):
                    try:
                        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    except ValueError:
                        dt = None
                else:
                    dt = val
                if dt:
                    if "starts_at" not in data or not data["starts_at"]:
                        data["starts_at"] = dt
                    if "ends_at" not in data or not data["ends_at"]:
                        data["ends_at"] = dt + timedelta(minutes=30)
            if "appointment_type" in data and data["appointment_type"]:
                if "reason" not in data or not data["reason"]:
                    data["reason"] = data["appointment_type"]
        return data

    @model_validator(mode="after")
    def validate_time_range(self) -> "PetAppointmentCreate":
        if self.starts_at is None:
            raise ValueError("starts_at (or scheduled_at) is required")
        if self.ends_at is None:
            raise ValueError("ends_at is required")
        if not self.reason:
            raise ValueError("reason (or appointment_type) is required")
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

    @computed_field
    @property
    def appointment_type(self) -> str:
        return self.reason

    @computed_field
    @property
    def scheduled_at(self) -> datetime:
        return self.starts_at


class AppointmentCancelRequest(BaseModel):
    reason: str | None = Field(None, max_length=255)


class AppointmentStatusRequest(BaseModel):
    status: Literal["confirmed", "completed", "no_show"]


class PetReminderCreate(BaseModel):
    kind: ReminderKind | None = None
    title: str | None = Field(None, max_length=255)
    details: str | None = Field(None, max_length=4000)
    due_at: datetime | None = None
    source_key: str | None = Field(None, max_length=255)

    @model_validator(mode="before")
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "reminder_type" in data and data["reminder_type"]:
                if "kind" not in data or not data["kind"]:
                    data["kind"] = data["reminder_type"]
            if "remind_at" in data and data["remind_at"]:
                if "due_at" not in data or not data["due_at"]:
                    from datetime import datetime

                    val = data["remind_at"]
                    if isinstance(val, str):
                        try:
                            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                        except ValueError:
                            dt = None
                    else:
                        dt = val
                    if dt:
                        data["due_at"] = dt
            if "message" in data and data["message"]:
                if "title" not in data or not data["title"]:
                    data["title"] = data["message"]
                if "details" not in data or not data["details"]:
                    data["details"] = data["message"]
            if "source_key" not in data or not data["source_key"]:
                import uuid

                data["source_key"] = f"manual:{uuid.uuid4()}"
        return data

    @model_validator(mode="after")
    def validate_required_fields(self) -> "PetReminderCreate":
        if self.kind is None:
            raise ValueError("kind (or reminder_type) is required")
        if not self.title:
            raise ValueError("title (or message) is required")
        if self.due_at is None:
            raise ValueError("due_at (or remind_at) is required")
        if not self.source_key:
            raise ValueError("source_key is required")
        return self


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

    @computed_field
    @property
    def reminder_type(self) -> str:
        return self.kind

    @computed_field
    @property
    def remind_at(self) -> datetime:
        return self.due_at

    @computed_field
    @property
    def message(self) -> str:
        return self.title
