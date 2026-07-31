"""ORM models for the Settings & Configuration module."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import TimestampMixin, UUIDPkMixin


class SystemSetting(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="general", index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PasswordPolicy(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "password_policies"

    min_length: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    require_uppercase: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_lowercase: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_digit: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_special_char: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_age_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    password_history_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_login_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    lockout_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BusinessRule(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "business_rules"

    rule_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    rule_value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
