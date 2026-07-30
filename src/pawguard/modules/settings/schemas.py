"""Pydantic schemas for Settings module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=0)
    category: str = Field(default="general", max_length=64)
    description: str | None = None
    is_encrypted: bool = False
    is_editable: bool = True


class SystemSettingUpdate(BaseModel):
    value: str | None = None
    description: str | None = None
    is_encrypted: bool | None = None
    is_editable: bool | None = None


class SystemSettingResponse(BaseModel):
    id: uuid.UUID
    key: str
    value: str
    category: str
    description: str | None
    is_encrypted: bool
    is_editable: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PasswordPolicyResponse(BaseModel):
    id: uuid.UUID
    min_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_digit: bool
    require_special_char: bool
    max_age_days: int
    password_history_count: int
    max_login_attempts: int
    lockout_duration_minutes: int
    is_active: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PasswordPolicyUpdate(BaseModel):
    min_length: int | None = Field(None, ge=6, le=128)
    require_uppercase: bool | None = None
    require_lowercase: bool | None = None
    require_digit: bool | None = None
    require_special_char: bool | None = None
    max_age_days: int | None = Field(None, ge=1, le=365)
    password_history_count: int | None = Field(None, ge=0, le=50)
    max_login_attempts: int | None = Field(None, ge=1, le=20)
    lockout_duration_minutes: int | None = Field(None, ge=1, le=1440)
    is_active: bool | None = None


class BusinessRuleCreate(BaseModel):
    rule_key: str = Field(..., min_length=1, max_length=255)
    rule_value: str = Field(..., min_length=0)
    description: str | None = None
    module: str = Field(..., max_length=64)


class BusinessRuleUpdate(BaseModel):
    rule_value: str | None = None
    description: str | None = None
    is_active: bool | None = None


class BusinessRuleResponse(BaseModel):
    id: uuid.UUID
    rule_key: str
    rule_value: str
    description: str | None
    module: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneralSettingsResponse(BaseModel):
    app_name: str
    environment: str
    debug: bool
    allowed_hosts: str
    cors_origins: str
    web_app_url: str
    admin_app_url: str


class EmailSettingsResponse(BaseModel):
    mail_from: str
    mail_host: str
    mail_port: int
    mail_use_tls: bool


class EmailSettingsUpdate(BaseModel):
    mail_from: str | None = None
    mail_host: str | None = None
    mail_port: int | None = Field(None, ge=1, le=65535)
    mail_username: str | None = None
    mail_password: str | None = None
    mail_use_tls: bool | None = None


class NotificationSettingsResponse(BaseModel):
    enable_push: bool
    enable_sms: bool
    enable_email: bool
    push_provider: str | None
    sms_provider: str | None


class StorageSettingsResponse(BaseModel):
    s3_bucket_name: str
    s3_region: str
    presigned_url_expiry_seconds: int
