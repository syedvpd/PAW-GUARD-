"""Pydantic schemas for the Volunteer Management module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.volunteer.models import VolunteerStatus


class VolunteerProfileCreate(BaseModel):
    emergency_contact_name: str = Field(..., min_length=1, max_length=255)
    emergency_contact_phone: str = Field(..., min_length=1, max_length=32)
    skills: str | None = None
    availability: str | None = Field(None, max_length=255)
    notes: str | None = None
    # Self-reported at application time. background_check_completed is staff-
    # verified and deliberately not settable here - see VolunteerProfileUpdate.
    medical_conditions: str | None = None
    animal_handling_experience: str | None = None


class VolunteerProfileUpdate(BaseModel):
    status: VolunteerStatus | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    skills: str | None = None
    availability: str | None = None
    notes: str | None = None
    medical_conditions: str | None = None
    animal_handling_experience: str | None = None
    background_check_completed: bool | None = None
    background_check_notes: str | None = None


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
    role_name: str = Field(..., min_length=1, max_length=64)
    start_at: datetime
    end_at: datetime
    capacity: int = Field(5, ge=1)


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

    model_config = ConfigDict(from_attributes=True)
