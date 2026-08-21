"""ORM models for in-app notifications and governance control engine."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Notification(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="general", index=True
    )
    is_broadcast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationPreference(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    enable_push: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enable_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enable_sms: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5), nullable=True)


class NotificationGlobalConfig(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """Level 1 Governance: Global push notification master status (ENABLED, DISABLED, PAUSED)."""

    __tablename__ = "notification_global_config"

    push_status: Mapped[str] = mapped_column(
        String(16), default="ENABLED", nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class NotificationModuleConfig(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """Level 2 Governance: Per-module push notification state (ENABLED, DISABLED, PAUSED)."""

    __tablename__ = "notification_module_configs"

    module_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    push_status: Mapped[str] = mapped_column(
        String(16), default="ENABLED", nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class NotificationTriggerConfig(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """Level 3 Governance: Trigger-specific rules, priority, and approval requirements."""

    __tablename__ = "notification_trigger_configs"

    trigger_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    module_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    push_status: Mapped[str] = mapped_column(
        String(16), default="ENABLED", nullable=False, index=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_priority: Mapped[str] = mapped_column(String(16), default="HIGH", nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class NotificationApprovalQueue(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """Pending & historical notifications in the Admin Approval Queue."""

    __tablename__ = "notification_approval_queue"

    trigger_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    recipient_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    target_user_ids: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="HIGH", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING_APPROVAL", nullable=False, index=True
    )
    pause_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationGovernanceAuditLog(UUIDPkMixin, Base):
    """Immutable audit trail of all governance actions, status changes, and approvals."""

    __tablename__ = "notification_governance_audit_logs"

    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("notification_approval_queue.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trigger_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
