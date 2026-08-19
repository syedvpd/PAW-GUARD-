"""Pydantic DTO schemas for Push Notification Governance and Admin Approval Engine."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GlobalConfigResponse(BaseModel):
    id: uuid.UUID
    push_status: str  # ENABLED, DISABLED, PAUSED
    reason: str | None = None
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GlobalConfigUpdate(BaseModel):
    push_status: str = Field(..., examples=["PAUSED"])
    reason: str | None = Field(None, examples=["Overnight quiet window testing"])


class ModuleConfigResponse(BaseModel):
    id: uuid.UUID
    module_name: str
    push_status: str  # ENABLED, DISABLED, PAUSED
    reason: str | None = None
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModuleConfigUpdate(BaseModel):
    push_status: str = Field(..., examples=["PAUSED"])
    reason: str | None = Field(None, examples=["Rescue notifications temporarily paused"])


class TriggerConfigResponse(BaseModel):
    id: uuid.UUID
    trigger_code: str
    module_name: str
    display_name: str
    push_status: str  # ENABLED, DISABLED, PAUSED
    email_enabled: bool
    requires_approval: bool
    default_priority: str  # HIGH, NORMAL, LOW
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TriggerConfigUpdate(BaseModel):
    push_status: str | None = Field(None, examples=["ENABLED"])
    email_enabled: bool | None = Field(None, examples=[True])
    requires_approval: bool | None = Field(None, examples=[True])
    default_priority: str | None = Field(None, examples=["HIGH"])


class ApprovalQueueItemResponse(BaseModel):
    id: uuid.UUID
    trigger_code: str
    module_name: str
    title: str
    body: str
    action_url: str | None = None
    image_url: str | None = None
    metadata_json: dict[str, Any] | list[Any] | None = None
    recipient_count: int
    target_user_ids: list[str] | None = None
    priority: str
    status: str  # PENDING_APPROVAL, APPROVED, REJECTED, PAUSED, SENT, FAILED, EXPIRED, BLOCKED
    pause_reason: str | None = None
    rejection_reason: str | None = None
    requested_by: uuid.UUID | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    paused_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalActionRequest(BaseModel):
    reason: str | None = Field(None, examples=["Incorrect location details"])


class GovernanceAuditLogResponse(BaseModel):
    id: uuid.UUID
    notification_id: uuid.UUID | None = None
    trigger_code: str
    module_name: str
    actor_user_id: uuid.UUID | None = None
    actor_role: str | None = None
    action: str
    previous_status: str | None = None
    new_status: str | None = None
    reason: str | None = None
    metadata_json: dict[str, Any] | list[Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationOverviewResponse(BaseModel):
    total_today: int
    pending_approval: int
    sent_today: int
    failed_today: int
    blocked_today: int
    paused_today: int
    rejected_today: int
    global_push_status: str
    global_pause_reason: str | None = None
