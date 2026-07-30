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
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    notification_type: str = "general"
    action_url: str | None = None


class BroadcastCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    notification_type: str = "broadcast"
    action_url: str | None = None


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
    enable_push: bool | None = None
    enable_email: bool | None = None
    enable_sms: bool | None = None
    quiet_hours_start: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")


class NotificationSend(BaseModel):
    user_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    notification_type: str = "general"
    action_url: str | None = None
    send_email: bool = False


class UnreadCountResponse(BaseModel):
    count: int
