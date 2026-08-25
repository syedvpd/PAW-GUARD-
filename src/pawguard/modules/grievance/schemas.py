"""Pydantic schemas for grievance/feedback module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from pawguard.modules.grievance.models import GrievanceStatus


class GrievanceCreate(BaseModel):
    reporter_name: str = Field(..., min_length=1, max_length=255, examples=["Priya Nair"])
    reporter_phone: str = Field(
        ...,
        min_length=5,
        max_length=32,
        pattern=r"^\+?[0-9\s\-()]+$",
        examples=["+1-555-0177"],
    )
    reporter_email: EmailStr | None = Field(None, examples=["priya.nair@example.com"])
    complaint_type: str = Field(..., min_length=1, max_length=128, examples=["Rescue Delay"])
    details: str = Field(
        ...,
        min_length=1,
        examples=["Reported an injured dog at 9am but the team arrived after 6 hours."],
    )


class GrievanceUpdate(BaseModel):
    status: GrievanceStatus | None = Field(None, examples=["investigating"])
    assigned_to_admin_id: uuid.UUID | None = None
    resolution_notes: str | None = Field(
        None, examples=["Dispatch delay traced to a vehicle shortage; process updated."]
    )


class GrievanceResponse(BaseModel):
    id: uuid.UUID
    reporter_name: str
    reporter_phone: str
    reporter_email: str | None
    complaint_type: str
    details: str
    status: GrievanceStatus
    assigned_to_admin_id: uuid.UUID | None
    resolution_notes: str | None
    sla_due_at: datetime | None
    first_responded_at: datetime | None
    escalation_level: int
    escalated_at: datetime | None
    escalated_to_admin_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GrievanceEscalate(BaseModel):
    escalated_to_admin_id: uuid.UUID
    reason: str | None = Field(None, examples=["SLA breached, needs senior review."])


class GrievanceListFilter(BaseModel):
    status: GrievanceStatus | None = None
    complaint_type: str | None = None
    assigned_to_admin_id: uuid.UUID | None = None
    search: str | None = None


class GrievanceAssign(BaseModel):
    assigned_to_admin_id: uuid.UUID


class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, examples=["We've dispatched an agent to follow up."])
    is_internal: bool = False


class CommentResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    is_internal: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceFeedbackCreate(BaseModel):
    rescue_case_id: uuid.UUID | None = None
    adoption_application_id: uuid.UUID | None = None
    rating: int = Field(..., ge=1, le=5, examples=[5])
    comments: str | None = Field(None, examples=["The whole team was wonderful, thank you!"])


class ServiceFeedbackResponse(BaseModel):
    id: uuid.UUID
    rescue_case_id: uuid.UUID | None
    adoption_application_id: uuid.UUID | None
    rating: int
    comments: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
