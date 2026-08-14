"""Pydantic schemas for the Emergency Rescue module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from pawguard.modules.rescue.models import (
    RescueEscalationType,
    RescueFailureReason,
    RescuePhysicalCondition,
    RescueSeverity,
    RescueStatus,
)

# Legacy free-text physical-condition values accepted from existing public
# clients, normalised to the canonical PRR 3.2 enum values. New submissions
# may use either the legacy labels or the canonical values.
_LEGACY_CONDITION_ALIASES: dict[str, RescuePhysicalCondition] = {
    "critical": RescuePhysicalCondition.CRITICAL,
    "critical/life threatening": RescuePhysicalCondition.CRITICAL,
    "life threatening": RescuePhysicalCondition.CRITICAL,
    "injured": RescuePhysicalCondition.INJURED,
    "fractured": RescuePhysicalCondition.INJURED,
    "fractured/injured": RescuePhysicalCondition.INJURED,
    "injured/fractured": RescuePhysicalCondition.INJURED,
    "sick": RescuePhysicalCondition.SICK,
    "contagious": RescuePhysicalCondition.SICK,
    "contagious disease/sick": RescuePhysicalCondition.SICK,
    "malnourished": RescuePhysicalCondition.MALNOURISHED,
    "stray": RescuePhysicalCondition.ABANDONED,
    "abandoned": RescuePhysicalCondition.ABANDONED,
    "abandoned/stray": RescuePhysicalCondition.ABANDONED,
}


def _normalise_physical_condition(value: object) -> RescuePhysicalCondition | object:
    """Coerce legacy labels and canonical values to the enum.

    Runs before Pydantic's type coercion so free-text values from existing
    public clients don't start failing with 422; unknown strings are passed
    through unchanged and surface as a normal enum validation error.
    """
    if isinstance(value, RescuePhysicalCondition):
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _LEGACY_CONDITION_ALIASES:
            return _LEGACY_CONDITION_ALIASES[key]
        try:
            return RescuePhysicalCondition(key)
        except ValueError:
            return value
    return value


# Legacy free-text failed-rescue reasons accepted from existing clients,
# normalised to the canonical PRR 3.3 outcome codes. Unknown strings are
# normalised to OTHER so a field agent can always log a failed rescue.
_LEGACY_FAILURE_REASON_ALIASES: dict[str, RescueFailureReason] = {
    "animal fled": RescueFailureReason.ANIMAL_FLED,
    "animal fled area": RescueFailureReason.ANIMAL_FLED,
    "fled": RescueFailureReason.ANIMAL_FLED,
    "area inaccessible": RescueFailureReason.AREA_INACCESSIBLE,
    "inaccessible": RescueFailureReason.AREA_INACCESSIBLE,
    "false report": RescueFailureReason.FALSE_REPORT,
    "false alarm": RescueFailureReason.FALSE_REPORT,
    "local intervention blocked": RescueFailureReason.LOCAL_INTERVENTION_BLOCKED,
    "intervention blocked": RescueFailureReason.LOCAL_INTERVENTION_BLOCKED,
    "blocked": RescueFailureReason.LOCAL_INTERVENTION_BLOCKED,
}


def normalise_failure_reason(value: object) -> RescueFailureReason:
    """Coerce a legacy reason string (or canonical value) to the enum.

    Unknown/missing strings fall back to OTHER so a failed rescue can always
    be logged in the field; canonical values pass through unchanged.
    """
    if isinstance(value, RescueFailureReason):
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _LEGACY_FAILURE_REASON_ALIASES:
            return _LEGACY_FAILURE_REASON_ALIASES[key]
        try:
            return RescueFailureReason(key)
        except ValueError:
            return RescueFailureReason.OTHER
    return RescueFailureReason.OTHER


class RescueRequestCreate(BaseModel):
    reporter_name: str = Field(..., min_length=1, max_length=255, examples=["John Smith"])
    reporter_phone: str = Field(..., min_length=1, max_length=32, examples=["+1-555-0123"])
    reporter_alternate_phone: str | None = Field(None, max_length=32, examples=["+1-555-0199"])
    reporter_email: EmailStr | None = Field(None, examples=["john.smith@example.com"])
    is_anonymous: bool = False

    location_address: str = Field(..., min_length=1, examples=["123 Main Street, Sector 4"])
    location_landmark: str | None = Field(None, examples=["Near Central Park entrance"])
    latitude: float | None = Field(None, ge=-90.0, le=90.0, examples=[17.4482])
    longitude: float | None = Field(None, ge=-180.0, le=180.0, examples=[78.3741])

    animal_count: int = Field(1, ge=1, examples=[1])
    physical_condition: RescuePhysicalCondition = Field(
        ..., examples=["fractured_injured"]
    )  # PRR 3.2 categories; legacy labels are normalised automatically
    behavioral_indicators: str | None = Field(None, examples=["Timid, appears malnourished"])
    # Reporter self-assessment on intake; coordinators refine during
    # verification (PRR 3.2 severity prioritization).
    severity: RescueSeverity = Field(
        RescueSeverity.MEDIUM, examples=["high"]
    )
    is_urgent: bool = Field(
        False, examples=[False]
    )  # PRR 3.1.1 urgent-alert banner flag
    # Media evidence from the intake wizard (PRR 3.2): up to 5 photos + short
    # video clips (50MB combined) as object keys from the storage module's
    # presigned-upload flow.
    media_evidence: list[str] | None = Field(
        None,
        max_length=5,
        description=(
            "Up to 5 media object keys (photos / short video) from the "
            "storage presigned-upload flow."
        ),
        examples=[["rescue/2026/08/barnaby_1.jpg"]],
    )
    # Temporal tracking extras (PRR 3.2): environmental factors and
    # additional reporter notes captured by the intake wizard.
    environmental_factors: str | None = Field(
        None, examples=["Heavy rain, flooding on Sector 4 roads"]
    )
    reporter_notes: str | None = Field(None, examples=["Dog appears friendly but scared"])

    # The 5-item cap is enforced by Field(max_length=5) above; this validator
    # only normalises the keys (strip whitespace, reject empties).
    @field_validator("media_evidence")
    @classmethod
    def _validate_media_evidence(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned: list[str] = []
        for key in value:
            key = key.strip()
            if not key:
                raise ValueError("Media object keys cannot be empty.")
            cleaned.append(key)
        return cleaned

    _normalise_condition = field_validator("physical_condition", mode="before")(
        _normalise_physical_condition
    )


class PublicRescueStatusResponse(BaseModel):
    """Public case-status lookup response (PRR 3.2 "my submitted case" view).

    Deliberately minimal: no reporter identity, no full address, no dispatch
    details - just what the reporter already knows plus the pipeline status so
    they can see where their case stands.
    """

    ticket_number: str
    status: RescueStatus
    severity: RescueSeverity
    animal_count: int
    created_at: datetime
    updated_at: datetime


class RescueMediaUploadUrlRequest(BaseModel):
    filename: str = Field(..., examples=["incident_photo1.jpg"])
    mime_type: str = Field(..., examples=["image/jpeg"])
    file_size: int = Field(..., ge=1, le=52428800, description="Max 50MB file size limit")


class RescueMediaUploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str


class RescueRequestUpdate(BaseModel):
    status: RescueStatus | None = None
    rejection_rationale: str | None = None
    # Coordinator severity refinement at verification (PRR 3.2).
    severity: RescueSeverity | None = Field(None, examples=["critical"])
    is_urgent: bool | None = Field(None, examples=[True])
    media_evidence: list[str] | None = Field(None, max_length=5)


class RescueDispatchCreate(BaseModel):
    assigned_driver_id: uuid.UUID | None = None
    # Additional field agents for the dispatch (PRR 3.2 multi-agent teams).
    # The legacy single-driver flow still works: `assigned_driver_id` is
    # mirrored into the dispatch-agent association table automatically.
    assigned_agent_ids: list[uuid.UUID] | None = Field(
        None,
        description=(
            "Field agents assigned to the dispatch. Combined with "
            "assigned_driver_id to form the full team."
        ),
        examples=[[uuid.UUID("a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d")]],
    )
    vehicle_id: str | None = Field(None, max_length=64)
    assigned_vehicle_id: uuid.UUID | None = Field(
        None,
        description="UUID of the ACTIVE fleet vehicle assigned to this dispatch.",
    )
    equipment_details: str | None = None
    # Escalation Protocol (PRR 3.3): agents request back-up personnel,
    # veterinary transport, or law enforcement support from the field.
    escalation_type: RescueEscalationType | None = Field(
        None, examples=["backup_personnel"]
    )
    escalation_notes: str | None = Field(
        None, examples=["Second team needed - dog is aggressive."]
    )
    notes: str | None = None


class RescueDispatchUpdate(BaseModel):
    assigned_driver_id: uuid.UUID | None = None
    assigned_agent_ids: list[uuid.UUID] | None = None
    vehicle_id: str | None = None
    assigned_vehicle_id: uuid.UUID | None = None
    equipment_details: str | None = None
    status: RescueStatus | str | None = None
    failure_reason: RescueFailureReason | str | None = None
    escalation_type: RescueEscalationType | str | None = None
    escalation_notes: str | None = None
    notes: str | None = None
    located_at: datetime | None = None
    rescued_at: datetime | None = None
    admitted_at: datetime | None = None
    failed_at: datetime | None = None


class RescueDispatchAgentResponse(BaseModel):
    id: uuid.UUID
    dispatch_id: uuid.UUID
    agent_id: uuid.UUID
    role: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RescueEscalateCreate(BaseModel):
    """Escalation Protocol request (PRR 3.3): settable post-dispatch via the
    dedicated escalate endpoint, not only at dispatch time."""

    escalation_type: RescueEscalationType = Field(..., examples=["backup_personnel"])
    escalation_notes: str | None = Field(
        None, examples=["Second team needed - dog is aggressive."]
    )


class RescueDispatchResponse(BaseModel):
    id: uuid.UUID
    rescue_request_id: uuid.UUID
    assigned_driver_id: uuid.UUID | None
    vehicle_id: str | None
    assigned_vehicle_id: uuid.UUID | None = None
    agents: list[RescueDispatchAgentResponse] = Field(default_factory=list)
    equipment_details: str | None
    dispatched_at: datetime
    located_at: datetime | None
    rescued_at: datetime | None
    admitted_at: datetime | None
    failed_at: datetime | None
    failure_reason: RescueFailureReason | None
    escalation_type: RescueEscalationType | None
    escalation_notes: str | None
    notes: str | None
    status: RescueStatus | None = None
    ticket_number: str | None = None


    _normalise_failure = field_validator("failure_reason", mode="before")(
        lambda v: None if v is None else normalise_failure_reason(v)
    )

    model_config = ConfigDict(from_attributes=True)


class AgentLocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, examples=[17.4482])
    longitude: float = Field(..., ge=-180.0, le=180.0, examples=[78.3741])


class NearbyAgentResponse(BaseModel):
    agent_id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    distance_km: float | None = None
    latitude: float | None = None
    longitude: float | None = None



class RescueReportCreate(BaseModel):
    notes: str | None = None
    photos: list[str] | None = Field(None, max_length=5)


class RescueReportResponse(BaseModel):
    id: uuid.UUID
    rescue_request_id: uuid.UUID
    agent_id: uuid.UUID
    notes: str | None
    photos: list[str] | None
    photo_urls: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _populate_photo_urls(cls, data: Any) -> Any:
        if hasattr(data, "photos") and not isinstance(data, dict):
            photos = getattr(data, "photos", None) or []
            urls = []
            if photos:
                from pawguard.services.storage_service import StorageService
                storage = StorageService()
                urls = [storage.generate_presigned_download_url(object_key=k) for k in photos if k]
            return {
                "id": data.id,
                "rescue_request_id": data.rescue_request_id,
                "agent_id": data.agent_id,
                "notes": data.notes,
                "photos": photos,
                "photo_urls": urls,
                "created_at": data.created_at,
            }
        return data

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
    physical_condition: RescuePhysicalCondition
    behavioral_indicators: str | None
    severity: RescueSeverity
    is_urgent: bool
    media_evidence: list[str] | None
    media_urls: list[str] = Field(default_factory=list)
    environmental_factors: str | None
    reporter_notes: str | None
    status: RescueStatus
    rejection_rationale: str | None
    coordinator_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    dispatch: RescueDispatchResponse | None = None
    reports: list[RescueReportResponse] = []

    @model_validator(mode="before")
    @classmethod
    def _populate_media_urls(cls, data: Any) -> Any:
        if hasattr(data, "media_evidence") and not isinstance(data, dict):
            keys = getattr(data, "media_evidence", None) or []
            urls = []
            if keys:
                from pawguard.services.storage_service import StorageService
                storage = StorageService()
                urls = [storage.generate_presigned_download_url(object_key=k) for k in keys if k]
            return {
                "id": data.id,
                "ticket_number": data.ticket_number,
                "reporter_name": data.reporter_name,
                "reporter_phone": data.reporter_phone,
                "reporter_alternate_phone": data.reporter_alternate_phone,
                "reporter_email": data.reporter_email,
                "is_anonymous": data.is_anonymous,
                "location_address": data.location_address,
                "location_landmark": data.location_landmark,
                "latitude": data.latitude,
                "longitude": data.longitude,
                "animal_count": data.animal_count,
                "physical_condition": data.physical_condition,
                "behavioral_indicators": data.behavioral_indicators,
                "severity": data.severity,
                "is_urgent": data.is_urgent,
                "media_evidence": keys,
                "media_urls": urls,
                "environmental_factors": data.environmental_factors,
                "reporter_notes": data.reporter_notes,
                "status": data.status,
                "rejection_rationale": data.rejection_rationale,
                "coordinator_id": getattr(data, "coordinator_id", None),
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "dispatch": getattr(data, "dispatch", None),
                "reports": getattr(data, "reports", []),
            }
        return data

    _normalise_condition = field_validator("physical_condition", mode="before")(
        _normalise_physical_condition
    )

    model_config = ConfigDict(from_attributes=True)


class RescueAssignCoordinator(BaseModel):
    """Payload for assigning a coordinator to a rescue case (PRR 3.2)."""

    coordinator_id: uuid.UUID = Field(
        ...,
        examples=["550e8400-e29b-41d4-a716-446655440000"],
        description="UUID of the user to assign as coordinator.",
    )
    notes: str | None = Field(
        None,
        examples=["Please prioritise this case — animal is in critical condition."],
        description="Optional notes for the coordinator.",
    )
