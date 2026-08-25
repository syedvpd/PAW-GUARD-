"""Pydantic schemas for the Volunteer Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.volunteer.models import ApplicationStatus, AttendanceStatus, VolunteerStatus


class VolunteerProfileCreate(BaseModel):
    emergency_contact_name: str = Field(..., min_length=1, max_length=255, examples=["Jane Doe"])
    emergency_contact_phone: str = Field(..., min_length=1, max_length=32, examples=["+1-555-0100"])
    skills: str | None = Field(None, examples=["Grooming, Transport, Photography"])
    availability: str | None = Field(None, max_length=255, examples=["Weekends, Evenings"])
    notes: str | None = Field(None, examples=["Available for emergency call-outs on weekends."])
    # Self-reported at application time. background_check_completed is staff-
    # verified and deliberately not settable here - see VolunteerProfileUpdate.
    medical_conditions: str | None = Field(None, examples=["None"])
    animal_handling_experience: str | None = Field(
        None, examples=["3 years volunteering at a local shelter, comfortable with large breeds."]
    )


class VolunteerProfileUpdate(BaseModel):
    status: VolunteerStatus | None = Field(None, examples=["active"])
    emergency_contact_name: str | None = Field(None, examples=["Jane Doe"])
    emergency_contact_phone: str | None = Field(None, examples=["+1-555-0100"])
    skills: str | None = Field(None, examples=["Grooming, Transport"])
    availability: str | None = Field(None, examples=["Weekends"])
    notes: str | None = Field(None, examples=["Onboarding completed."])
    medical_conditions: str | None = Field(None, examples=["None"])
    animal_handling_experience: str | None = Field(
        None, examples=["Comfortable with large breeds."]
    )
    background_check_completed: bool | None = Field(None, examples=[True])
    background_check_notes: str | None = Field(None, examples=["Clear, verified 2026-07-20."])


class VolunteerProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: VolunteerStatus
    emergency_contact_name: str
    emergency_contact_phone: str
    skills: str | None
    availability: str | None
    notes: str | None
    medical_conditions: str | None
    animal_handling_experience: str | None
    background_check_completed: bool
    background_check_notes: str | None
    created_at: datetime
    updated_at: datetime
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)


class VolunteerShiftCreate(BaseModel):
    shelter_facility_id: uuid.UUID | None = None
    role_name: str = Field(..., min_length=1, max_length=64, examples=["Dog Walking"])
    start_at: datetime = Field(..., examples=["2026-08-01T09:00:00Z"])
    end_at: datetime = Field(..., examples=["2026-08-01T12:00:00Z"])
    capacity: int = Field(5, ge=1, examples=[5])


class VolunteerShiftResponse(BaseModel):
    id: uuid.UUID
    shelter_facility_id: uuid.UUID | None
    role_name: str
    start_at: datetime
    end_at: datetime
    capacity: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ShiftAttendanceResponse(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    volunteer_id: uuid.UUID
    check_in_at: datetime | None
    check_out_at: datetime | None
    hours_logged: float | None
    status: AttendanceStatus
    no_show_reason: str | None
    no_show_marked_by: uuid.UUID | None
    no_show_marked_at: datetime | None
    cancelled_reason: str | None
    cancelled_by: uuid.UUID | None
    cancelled_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ShiftAttendanceWithShiftResponse(ShiftAttendanceResponse):
    shift: VolunteerShiftResponse | None = None


class ShiftAttendanceNoShow(BaseModel):
    reason: str = Field(
        ..., min_length=1, max_length=1000, examples=["Did not arrive; no notice given."]
    )


class ShiftAttendanceCancel(BaseModel):
    reason: str | None = Field(
        None, max_length=1000, examples=["Volunteer had a scheduling conflict."]
    )


class VolunteerServiceSummary(BaseModel):
    """Verified service totals used to issue a service certificate (PRR 3.9)."""

    volunteer_id: uuid.UUID
    total_hours: float
    shifts_count: int
    period_start: datetime | None
    period_end: datetime | None
    role_summary: str


class VolunteerApplicationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: ApplicationStatus
    emergency_contact_name: str
    emergency_contact_phone: str
    skills: str | None
    availability: str | None
    notes: str | None
    medical_conditions: str | None
    animal_handling_experience: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)


class VolunteerApplicationReject(BaseModel):
    reason: str = Field(
        ..., min_length=10, max_length=1000, examples=["Incomplete background check."]
    )


class VolunteerLifecycleStatus(BaseModel):
    """Current volunteer lifecycle state for the authenticated user."""

    status: str = Field(
        ...,
        description="Lifecycle state: NOT_APPLIED, PENDING, ACTIVE, REJECTED, INACTIVE",
        examples=["PENDING"],
    )
    application: VolunteerApplicationResponse | None = None
    profile: VolunteerProfileResponse | None = None
    can_apply: bool = Field(
        ...,
        description="Whether the user can submit a new application",
    )
    can_reapply: bool = Field(
        ...,
        description="Whether the user can reapply after rejection",
    )
