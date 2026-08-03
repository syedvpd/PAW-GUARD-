"""ORM models for the custom authentication system: identity, sessions, tokens, RBAC, audit."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.core.constants import DeviceType
from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class AuthAuditEventType(StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    REFRESH = "refresh"
    REFRESH_REUSE_DETECTED = "refresh_reuse_detected"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    EMAIL_VERIFICATION_REQUESTED = "email_verification_requested"
    EMAIL_VERIFIED = "email_verified"
    MFA_ENROLLED = "mfa_enrolled"
    MFA_VERIFIED = "mfa_verified"
    MFA_FAILED = "mfa_failed"
    MFA_DISABLED = "mfa_disabled"
    SESSION_REVOKED = "session_revoked"
    GRIEVANCE_UPDATED = "grievance_updated"
    GRIEVANCE_ASSIGNED = "grievance_assigned"
    DOG_REGISTERED = "dog_registered"
    DOG_UPDATED = "dog_updated"
    DOG_STATUS_CHANGED = "dog_status_changed"
    DOG_WEIGHT_RECORDED = "dog_weight_recorded"
    DOG_DELETED = "dog_deleted"
    BULK_DOG_STATUS_UPDATED = "bulk_dog_status_updated"
    BULK_DOG_DELETED = "bulk_dog_deleted"
    RESCUE_REPORTED = "rescue_reported"
    RESCUE_VERIFIED = "rescue_verified"
    RESCUE_REJECTED = "rescue_rejected"
    RESCUE_DISPATCHED = "rescue_dispatched"
    RESCUE_STATUS_UPDATED = "rescue_status_updated"
    RESCUE_DELETED = "rescue_deleted"
    BULK_RESCUE_STATUS_UPDATED = "bulk_rescue_status_updated"
    BULK_RESCUE_DELETED = "bulk_rescue_deleted"
    ADOPTION_SUBMITTED = "adoption_submitted"
    ADOPTION_UPDATED = "adoption_updated"
    ADOPTION_STATUS_CHANGED = "adoption_status_changed"
    ADOPTION_AGREEMENT_GENERATED = "adoption_agreement_generated"
    ADOPTION_DELETED = "adoption_deleted"
    BULK_ADOPTION_STATUS_UPDATED = "bulk_adoption_status_updated"
    BULK_ADOPTION_DELETED = "bulk_adoption_deleted"
    SHELTER_CREATED = "shelter_created"
    SHELTER_UPDATED = "shelter_updated"
    KENNEL_ASSIGNED = "kennel_assigned"
    KENNEL_SANITATION_UPDATED = "kennel_sanitation_updated"
    TRANSFER_REQUESTED = "transfer_requested"
    TRANSFER_CONFIRMED = "transfer_confirmed"
    CARE_LOG_SUBMITTED = "care_log_submitted"
    MEDICAL_RECORD_CREATED = "medical_record_created"
    MEDICAL_RECORD_UPDATED = "medical_record_updated"
    MEDICAL_RECORD_DELETED = "medical_record_deleted"
    VACCINATION_RECORDED = "vaccination_recorded"
    FLEET_VEHICLE_CREATED = "fleet_vehicle_created"
    FLEET_VEHICLE_UPDATED = "fleet_vehicle_updated"
    FLEET_VEHICLE_DELETED = "fleet_vehicle_deleted"
    FLEET_EQUIPMENT_CHECKED_OUT = "fleet_equipment_checked_out"
    FLEET_EQUIPMENT_RETURNED = "fleet_equipment_returned"
    FOSTER_APPLICATION_SUBMITTED = "foster_application_submitted"
    FOSTER_APPLICATION_UPDATED = "foster_application_updated"
    FOSTER_PLACEMENT_CREATED = "foster_placement_created"
    FOSTER_PLACEMENT_ENDED = "foster_placement_ended"
    FOSTER_SUPPLY_DISPATCHED = "foster_supply_dispatched"
    FOSTER_DELETED = "foster_deleted"
    INVENTORY_ITEM_CREATED = "inventory_item_created"
    INVENTORY_ITEM_UPDATED = "inventory_item_updated"
    INVENTORY_ITEM_DELETED = "inventory_item_deleted"
    INVENTORY_STOCK_ADJUSTED = "inventory_stock_adjusted"
    LOST_FOUND_REPORTED = "lost_found_reported"
    LOST_FOUND_UPDATED = "lost_found_updated"
    LOST_FOUND_RESOLVED = "lost_found_resolved"
    LOST_FOUND_DELETED = "lost_found_deleted"
    LOST_FOUND_CLAIM_SUBMITTED = "lost_found_claim_submitted"
    LOST_FOUND_CLAIM_REVIEWED = "lost_found_claim_reviewed"
    NOTIFICATION_SENT = "notification_sent"
    PORTAL_POST_CREATED = "portal_post_created"
    PORTAL_POST_UPDATED = "portal_post_updated"
    PORTAL_POST_DELETED = "portal_post_deleted"
    VOLUNTEER_APPLICATION_SUBMITTED = "volunteer_application_submitted"
    VOLUNTEER_APPLICATION_UPDATED = "volunteer_application_updated"
    VOLUNTEER_SHIFT_CREATED = "volunteer_shift_created"
    VOLUNTEER_SHIFT_UPDATED = "volunteer_shift_updated"
    VOLUNTEER_DELETED = "volunteer_deleted"
    VOLUNTEER_CERTIFICATE_ISSUED = "volunteer_certificate_issued"
    DONATION_RECEIVED = "donation_received"
    DONATION_ORDER_CREATED = "donation_order_created"
    DONOR_REGISTERED = "donor_registered"
    DONATION_REFUNDED = "donation_refunded"
    DONATION_RECEIPT_ISSUED = "donation_receipt_issued"
    DONATION_STATUS_CHANGED = "donation_status_changed"
    DONOR_PROFILE_UPDATED = "donor_profile_updated"
    DONOR_PROFILE_DELETED = "donor_profile_deleted"
    SPONSORSHIP_CREATED = "sponsorship_created"
    SPONSORSHIP_CANCELLED = "sponsorship_cancelled"
    SPONSORSHIP_PAUSED = "sponsorship_paused"
    SPONSORSHIP_CHARGED = "sponsorship_charged"
    DONATION_CAMPAIGN_CREATED = "donation_campaign_created"
    DONATION_CAMPAIGN_UPDATED = "donation_campaign_updated"
    DONATION_CAMPAIGN_COMPLETED = "donation_campaign_completed"
    DONATION_CAMPAIGN_DELETED = "donation_campaign_deleted"
    SETTINGS_UPDATED = "settings_updated"
    REGISTERED = "registered"
    ACCOUNT_LOCKED = "account_locked"
    PROFILE_UPDATED = "profile_updated"
    OAUTH_LOGIN = "oauth_login"
    OAUTH_LINKED = "oauth_linked"
    OAUTH_UNLINKED = "oauth_unlinked"
    ADMIN_USER_CREATED = "admin_user_created"
    ADMIN_USER_UPDATED = "admin_user_updated"
    ADMIN_USER_DELETED = "admin_user_deleted"
    ADMIN_ROLE_CREATED = "admin_role_created"
    ADMIN_ROLE_UPDATED = "admin_role_updated"
    ADMIN_ROLE_DELETED = "admin_role_deleted"
    FINANCE_ACCOUNT_CREATED = "finance_account_created"
    FINANCE_ACCOUNT_UPDATED = "finance_account_updated"
    FINANCE_ACCOUNT_DELETED = "finance_account_deleted"
    FINANCE_TRANSACTION_CREATED = "finance_transaction_created"
    FINANCE_TRANSACTION_STATUS_UPDATED = "finance_transaction_status_updated"
    FINANCE_TRANSACTION_DELETED = "finance_transaction_deleted"
    FINANCE_DONATIONS_RECONCILED = "finance_donations_reconciled"
    FINANCE_BUDGET_CREATED = "finance_budget_created"
    FINANCE_BUDGET_ITEM_ADDED = "finance_budget_item_added"
    FINANCE_RECURRING_CREATED = "finance_recurring_created"


class Role(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles"
    )
    users: Mapped[list["User"]] = relationship(secondary="user_roles", back_populates="roles")


class Permission(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class User(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list["Role"]] = relationship(secondary="user_roles", back_populates="users")
    # passive_deletes: these FKs are ON DELETE CASCADE at the DB level: let
    # postgres remove the children instead of the ORM issuing per-row
    # UPDATE ... SET user_id = NULL (which fails - user_id is NOT NULL).
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        back_populates="user", passive_deletes=True
    )

    __table_args__ = (Index("ix_users_email_lower", "email"),)


class UserSession(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_type: Mapped[DeviceType] = mapped_column(
        String(16), default=DeviceType.UNKNOWN, nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="session")


class RefreshToken(UUIDPkMixin, Base):
    __tablename__ = "refresh_tokens"

    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    session: Mapped["UserSession"] = relationship(back_populates="refresh_tokens")


class MFADevice(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "mfa_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_type: Mapped[str] = mapped_column(String(16), default="totp", nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PasswordResetToken(UUIDPkMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmailVerificationToken(UUIDPkMixin, Base):
    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OAuthAccount(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "oauth_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    picture_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped["User"] = relationship(back_populates="oauth_accounts")

    __table_args__ = (
        Index("ix_oauth_accounts_provider", "provider", "provider_user_id", unique=True),
    )


class AuthAuditLog(UUIDPkMixin, Base):
    __tablename__ = "auth_audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
