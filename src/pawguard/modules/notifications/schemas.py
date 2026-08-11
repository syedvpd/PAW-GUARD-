"""Pydantic schemas for notifications."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    body: str
    notification_type: str | None
    is_broadcast: bool
    is_read: bool
    action_url: str | None
    created_at: datetime
    sent_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationCreate(BaseModel):
    user_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255, examples=["Vaccination Renewal Due"])
    body: str = Field(..., min_length=1, examples=["Barnaby's rabies booster is due in 14 days."])
    notification_type: str = Field("general", examples=["reminder"])
    action_url: str | None = Field(None, examples=["/dogs/DOG-2026-0412"])


class BroadcastCreate(BaseModel):
    title: str = Field(
        ..., min_length=1, max_length=255, examples=["Shelter Closed for Maintenance"]
    )
    body: str = Field(
        ..., min_length=1, examples=["Central Shelter will be closed on Aug 5 for repairs."]
    )
    notification_type: str = Field("broadcast", examples=["announcement"])
    action_url: str | None = Field(None, examples=["/announcements/shelter-closure"])
    target_roles: list[str] | None = Field(
        None,
        examples=[["rescue_centre_admin", "shelter_manager"]],
        description="Broadcast to all active users holding any of these roles.",
    )


class NotificationPreferenceResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    enable_push: bool
    enable_email: bool
    enable_sms: bool
    quiet_hours_start: str | None
    quiet_hours_end: str | None

    model_config = ConfigDict(from_attributes=True)


class NotificationPreferenceUpdate(BaseModel):
    enable_push: bool | None = Field(None, examples=[True])
    enable_email: bool | None = Field(None, examples=[True])
    enable_sms: bool | None = Field(None, examples=[False])
    quiet_hours_start: str | None = Field(None, pattern=r"^\d{2}:\d{2}$", examples=["22:00"])
    quiet_hours_end: str | None = Field(None, pattern=r"^\d{2}:\d{2}$", examples=["07:00"])


class NotificationSend(BaseModel):
    user_id: uuid.UUID | None = Field(
        None,
        examples=["550e8400-e29b-41d4-a716-446655440000"],
        description="Target user (required unless target_roles is provided).",
    )
    title: str = Field(..., min_length=1, max_length=255, examples=["Adoption Application Update"])
    body: str = Field(
        ..., min_length=1, examples=["Your application for Barnaby has been approved!"]
    )
    notification_type: str = Field("general", examples=["adoption_update"])
    action_url: str | None = Field(None, examples=["/adoptions/my-applications"])
    send_email: bool = False
    target_roles: list[str] | None = Field(
        None,
        examples=[["rescue_centre_admin"]],
        description="Send to all active users holding any of these roles.",
    )


class UnreadCountResponse(BaseModel):
    count: int
