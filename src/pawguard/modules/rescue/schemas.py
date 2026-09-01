"""Pydantic schemas for the Emergency Rescue module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from pawguard.modules.lost_found.schemas import ReportMediaResponse
from pawguard.modules.rescue.models import (
    RescueEscalationStatus,
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
    severity: RescueSeverity = Field(RescueSeverity.MEDIUM, examples=["high"])
    is_urgent: bool = Field(False, examples=[False])  # PRR 3.1.1 urgent-alert banner flag
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
    photo_object_keys: list[str] | None = Field(None, max_length=5, examples=[["rescue/file1.jpg"]])
    video_object_key: str | None = Field(None, max_length=512, examples=["rescue/video1.mp4"])
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

    @field_validator("photo_object_keys")
    @classmethod
    def _validate_photo_object_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned: list[str] = []
        for key in value:
            key = key.strip()
            if not key:
                raise ValueError("Photo object keys cannot be empty.")
            if not key.startswith("rescue/"):
                raise ValueError(
                    "Each photo key must reference a rescue upload (expected prefix 'rescue/')."
                )
            cleaned.append(key)
        return cleaned

    @field_validator("video_object_key")
    @classmethod
    def _validate_video_object_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("video_object_key cannot be empty.")
        if not value.startswith("rescue/"):
            raise ValueError(
                "video_object_key must reference a rescue upload (expected prefix 'rescue/')."
            )
        return value

    _normalise_condition = field_validator("physical_condition", mode="before")(
        _normalise_physical_condition
    )


class PublicRescueStatusResponse(BaseModel):
    """Public case-status lookup response (PRR 3.2 "my submitted case" view)."""

    ticket_number: str
    status: RescueStatus
    severity: RescueSeverity
    animal_count: int
    location_address: str | None = None
    is_urgent: bool = False
    rejection_rationale: str | None = None
    estimated_arrival_minutes: int | None = None
    eta_display: str | None = None
    assigned_vehicle_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RescueMediaUploadUrlRequest(BaseModel):
    filename: str = Field(..., examples=["incident_photo1.jpg"])
    mime_type: str = Field(..., examples=["image/jpeg"])
    file_size: int = Field(..., ge=1, le=104857600, description="Max 100MB file size limit")


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
    photo_object_keys: list[str] | None = Field(None, max_length=5)
    video_object_key: str | None = Field(None, max_length=512)


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
    escalation_type: RescueEscalationType | None = Field(None, examples=["backup_personnel"])
    escalation_notes: str | None = Field(None, examples=["Second team needed - dog is aggressive."])
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
    # Centre Admin updates the escalation lifecycle (PRR 3.3).
    # Cannot be set to a non-NONE value unless escalation_type exists.
    escalation_status: RescueEscalationStatus | None = None
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
    agent_name: str | None = None
    agent_email: str | None = None
    accepted_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _populate_agent_details(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        obj_dict = getattr(data, "__dict__", {})
        agent_obj = obj_dict.get("agent", None)
        return {
            "id": getattr(data, "id", None),
            "dispatch_id": getattr(data, "dispatch_id", None),
            "agent_id": getattr(data, "agent_id", None),
            "role": getattr(data, "role", None),
            "agent_name": getattr(agent_obj, "full_name", None) if agent_obj else None,
            "agent_email": getattr(agent_obj, "email", None) if agent_obj else None,
            "accepted_at": getattr(data, "accepted_at", None),
        }

    model_config = ConfigDict(from_attributes=True)


class RescueEscalateCreate(BaseModel):
    """Escalation Protocol request (PRR 3.3): settable post-dispatch via the
    dedicated escalate endpoint, not only at dispatch time."""

    escalation_type: RescueEscalationType = Field(..., examples=["backup_personnel"])
    escalation_notes: str | None = Field(None, examples=["Second team needed - dog is aggressive."])


class RescueDispatchResponse(BaseModel):
    id: uuid.UUID
    rescue_request_id: uuid.UUID
    assigned_driver_id: uuid.UUID | None = None
    driver_name: str | None = None
    driver_email: str | None = None
    vehicle_id: str | None = None
    assigned_vehicle_id: uuid.UUID | None = None
    agents: list[RescueDispatchAgentResponse] = Field(default_factory=list)
    equipment_details: str | None = None
    dispatched_at: datetime
    accepted_at: datetime | None = None
    located_at: datetime | None = None
    rescued_at: datetime | None = None
    admitted_at: datetime | None = None
    failed_at: datetime | None = None
    failure_reason: RescueFailureReason | None = None
    escalation_type: RescueEscalationType | None = None
    escalation_notes: str | None = None
    escalation_status: RescueEscalationStatus = RescueEscalationStatus.NONE
    notes: str | None = None
    status: RescueStatus | None = None
    ticket_number: str | None = None

    # Rescue case details & evidence for assigned Rescue Agents and Admins
    location_address: str | None = None
    location_landmark: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    reporter_name: str | None = None
    reporter_phone: str | None = None
    reporter_notes: str | None = None
    physical_condition: str | None = None
    behavioral_indicators: str | None = None
    severity: str | None = None
    is_urgent: bool | None = None
    animal_count: int | None = None
    media_evidence: list[str] | None = None
    media_urls: list[str] = Field(default_factory=list)
    photo_urls: list[str] = Field(default_factory=list)
    photo_object_keys: list[str] = Field(default_factory=list)
    video_url: str | None = None
    video_object_key: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _populate_driver_details(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        obj_dict = getattr(data, "__dict__", {})
        driver_obj = obj_dict.get("driver", None)
        agents_val = obj_dict.get("agents", getattr(data, "agents", []))
        req = obj_dict.get("rescue_request", getattr(data, "rescue_request", None))

        keys = getattr(req, "media_evidence", None) or [] if req else []
        photo_keys = []
        video_key = None
        video_exts = (".mp4", ".webm", ".mov", ".quicktime")
        for k in keys:
            if not k:
                continue
            k_lower = k.lower()
            if any(k_lower.endswith(ext) for ext in video_exts) or "video" in k_lower:
                if video_key is None:
                    video_key = k
            else:
                photo_keys.append(k)

        urls = []
        photo_urls = []
        video_url = None
        if keys:
            from pawguard.services.storage_service import get_storage_service

            storage = get_storage_service()
            try:
                urls = [storage.generate_presigned_download_url(object_key=k) for k in keys if k]
                photo_urls = [
                    storage.generate_presigned_download_url(object_key=k) for k in photo_keys if k
                ]
                if video_key:
                    video_url = storage.generate_presigned_download_url(object_key=video_key)
            except Exception:
                urls = []
                photo_urls = []
                video_url = None

        return {
            "id": getattr(data, "id", None),
            "rescue_request_id": getattr(data, "rescue_request_id", None),
            "assigned_driver_id": getattr(data, "assigned_driver_id", None),
            "driver_name": getattr(driver_obj, "full_name", None) if driver_obj else None,
            "driver_email": getattr(driver_obj, "email", None) if driver_obj else None,
            "vehicle_id": getattr(data, "vehicle_id", None),
            "assigned_vehicle_id": getattr(data, "assigned_vehicle_id", None),
            "agents": agents_val,
            "equipment_details": getattr(data, "equipment_details", None),
            "dispatched_at": getattr(data, "dispatched_at", None),
            "accepted_at": getattr(data, "accepted_at", None),
            "located_at": getattr(data, "located_at", None),
            "rescued_at": getattr(data, "rescued_at", None),
            "admitted_at": getattr(data, "admitted_at", None),
            "failed_at": getattr(data, "failed_at", None),
            "failure_reason": getattr(data, "failure_reason", None),
            "escalation_type": getattr(data, "escalation_type", None),
            "escalation_notes": getattr(data, "escalation_notes", None),
            "escalation_status": getattr(data, "escalation_status", None)
            or RescueEscalationStatus.NONE,
            "notes": getattr(data, "notes", None),
            "status": getattr(req, "status", getattr(data, "status", None))
            if req
            else getattr(data, "status", None),
            "ticket_number": getattr(req, "ticket_number", getattr(data, "ticket_number", None))
            if req
            else getattr(data, "ticket_number", None),
            "location_address": getattr(req, "location_address", None) if req else None,
            "location_landmark": getattr(req, "location_landmark", None) if req else None,
            "latitude": float(req.latitude) if (req and req.latitude is not None) else None,
            "longitude": float(req.longitude) if (req and req.longitude is not None) else None,
            "reporter_name": getattr(req, "reporter_name", None) if req else None,
            "reporter_phone": getattr(req, "reporter_phone", None) if req else None,
            "reporter_notes": getattr(req, "reporter_notes", None) if req else None,
            "physical_condition": str(req.physical_condition)
            if (req and req.physical_condition)
            else None,
            "behavioral_indicators": getattr(req, "behavioral_indicators", None) if req else None,
            "severity": str(req.severity) if (req and req.severity) else None,
            "is_urgent": getattr(req, "is_urgent", None) if req else None,
            "animal_count": getattr(req, "animal_count", None) if req else None,
            "media_evidence": keys,
            "media_urls": urls,
            "photo_urls": photo_urls,
            "photo_object_keys": photo_keys,
            "video_url": video_url,
            "video_object_key": video_key,
        }

    _normalise_failure = field_validator("failure_reason", mode="before")(
        lambda v: None if v is None else normalise_failure_reason(v)
    )

    model_config = ConfigDict(from_attributes=True)


class AgentLocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


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
                from pawguard.services.storage_service import get_storage_service

                storage = get_storage_service()
                try:
                    urls = [
                        storage.generate_presigned_download_url(object_key=k) for k in photos if k
                    ]
                except Exception:
                    urls = []
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
    photo_urls: list[str] = Field(default_factory=list)
    photo_object_keys: list[str] = Field(default_factory=list)
    video_url: str | None = None
    video_object_key: str | None = None
    environmental_factors: str | None
    reporter_notes: str | None
    status: RescueStatus
    rejection_rationale: str | None
    coordinator_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    dispatch: RescueDispatchResponse | None = None
    reports: list[RescueReportResponse] = []
    dog_profile_id: uuid.UUID | None = None
    media: list[ReportMediaResponse] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _populate_media_urls(cls, data: Any) -> Any:
        if hasattr(data, "media_evidence") and not isinstance(data, dict):
            keys = getattr(data, "media_evidence", None) or []
            photo_keys = []
            video_key = None
            video_exts = (".mp4", ".webm", ".mov", ".quicktime")

            for k in keys:
                if not k:
                    continue
                k_lower = k.lower()
                if any(k_lower.endswith(ext) for ext in video_exts) or "video" in k_lower:
                    if video_key is None:
                        video_key = k
                else:
                    photo_keys.append(k)

            # Safe relationship inspection to prevent MissingGreenlet errors in async SQLAlchemy
            obj_dict = getattr(data, "__dict__", {})
            dispatch_val = obj_dict.get("dispatch", None)
            reports_val = obj_dict.get("reports", [])
            media_val = obj_dict.get("media", [])
            dog_prof = obj_dict.get("dog_profile", None)
            dog_profile_id = getattr(dog_prof, "id", None) if dog_prof else None

            # Also inspect media rows if media_evidence was empty
            if not keys and media_val:
                for m in media_val:
                    m_type = getattr(m, "media_type", "")
                    m_key = getattr(m, "object_key", "")
                    if m_key:
                        if m_type == "video" or any(
                            m_key.lower().endswith(ext) for ext in video_exts
                        ):
                            if video_key is None:
                                video_key = m_key
                        else:
                            photo_keys.append(m_key)
                keys = photo_keys + ([video_key] if video_key else [])

            urls = []
            photo_urls = []
            video_url = None
            if keys:
                from pawguard.services.storage_service import get_storage_service

                storage = get_storage_service()
                try:
                    urls = [
                        storage.generate_presigned_download_url(object_key=k) for k in keys if k
                    ]
                    photo_urls = [
                        storage.generate_presigned_download_url(object_key=k)
                        for k in photo_keys
                        if k
                    ]
                    if video_key:
                        video_url = storage.generate_presigned_download_url(object_key=video_key)
                except Exception:
                    urls = []
                    photo_urls = []
                    video_url = None

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
                "photo_urls": photo_urls,
                "photo_object_keys": photo_keys,
                "video_url": video_url,
                "video_object_key": video_key,
                "environmental_factors": data.environmental_factors,
                "reporter_notes": data.reporter_notes,
                "status": data.status,
                "rejection_rationale": data.rejection_rationale,
                "coordinator_id": getattr(data, "coordinator_id", None),
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "dispatch": dispatch_val,
                "reports": reports_val,
                "dog_profile_id": dog_profile_id,
                "media": media_val,
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


class AgentAvailabilityResponse(BaseModel):
    """Dynamic availability of a rescue agent (PRR 3.2 coordinator selection)."""

    agent_id: uuid.UUID
    name: str
    status: str  # "available" | "busy"
    active_dispatch_id: uuid.UUID | None = None
    last_heartbeat: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class VehicleAvailabilityResponse(BaseModel):
    """Dynamic availability of a fleet vehicle (PRR 3.2 coordinator selection)."""

    vehicle_id: uuid.UUID
    license_plate: str
    vehicle_type: str | None = None
    operational_status: str
    availability: str  # "available" | "assigned" | "maintenance" | "out_of_service"
    active_dispatch_id: uuid.UUID | None = None


class RescueTrackingResponse(BaseModel):
    """GPS tracking session state for a rescue dispatch."""

    request_id: uuid.UUID
    tracking_active: bool
    started_at: str | None = None
    stopped_at: str | None = None


class RescueAgentLocation(BaseModel):
    agent_id: uuid.UUID
    latitude: float | None = None
    longitude: float | None = None
    last_heartbeat: str | None = None
    updated_at: str | None = None


class RescueLocationResponse(BaseModel):
    request_id: uuid.UUID
    agents: list[RescueAgentLocation] = Field(default_factory=list)
    vehicle: None = None
    updated_at: str | None = None


class RescueEventResponse(BaseModel):
    event_type: str
    actor_id: uuid.UUID | None = None
    created_at: str
    metadata: dict[str, Any] | None = None


class RescueDispatchCountsResponse(BaseModel):
    """Centre-wide aggregate counts for the Rescue Centre Admin dashboard.

    escalated_dispatches counts only *active* (unresolved) escalations so
    the dashboard badge matches the list returned by ?escalated=true.
    """

    total_dispatches: int
    active_dispatches: int
    escalated_dispatches: int
    failed_dispatches: int
