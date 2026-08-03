"""Pydantic schemas for Settings module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingCreate(BaseModel):
    key: str = Field(
        ..., min_length=1, max_length=255, examples=["max_rescue_dispatch_radius_km"]
    )
    value: str = Field(..., min_length=0, examples=["25"])
    category: str = Field(default="general", max_length=64, examples=["rescue"])
    description: str | None = Field(
        None, examples=["Maximum radius for auto-assigning field agents."]
    )
    is_encrypted: bool = False
    is_editable: bool = True


class SystemSettingUpdate(BaseModel):
    value: str | None = Field(None, examples=["30"])
    description: str | None = Field(None, examples=["Updated description."])
    is_encrypted: bool | None = Field(None, examples=[False])
    is_editable: bool | None = Field(None, examples=[True])


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
    min_length: int | None = Field(None, ge=6, le=128, examples=[10])
    require_uppercase: bool | None = Field(None, examples=[True])
    require_lowercase: bool | None = Field(None, examples=[True])
    require_digit: bool | None = Field(None, examples=[True])
    require_special_char: bool | None = Field(None, examples=[False])
    max_age_days: int | None = Field(None, ge=1, le=365, examples=[90])
    password_history_count: int | None = Field(None, ge=0, le=50, examples=[5])
    max_login_attempts: int | None = Field(None, ge=1, le=20, examples=[5])
    lockout_duration_minutes: int | None = Field(None, ge=1, le=1440, examples=[15])
    is_active: bool | None = Field(None, examples=[True])


class BusinessRuleCreate(BaseModel):
    rule_key: str = Field(..., min_length=1, max_length=255, examples=["adoption_lock_status"])
    rule_value: str = Field(..., min_length=0, examples=["home_check"])
    description: str | None = Field(None, examples=["Status at which a dog's profile locks."])
    module: str = Field(..., max_length=64, examples=["adoption"])


class BusinessRuleUpdate(BaseModel):
    rule_value: str | None = Field(None, examples=["approved"])
    description: str | None = Field(None, examples=["Updated description."])
    is_active: bool | None = Field(None, examples=[True])


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
    mail_from: str | None = Field(None, examples=["no-reply@pawguard.org"])
    mail_host: str | None = Field(None, examples=["smtp.mailgun.org"])
    mail_port: int | None = Field(None, ge=1, le=65535, examples=[587])
    mail_username: str | None = Field(None, examples=["postmaster@pawguard.org"])
    mail_password: str | None = Field(None, examples=["********"])
    mail_use_tls: bool | None = Field(None, examples=[True])


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


class PublicContentResponse(BaseModel):
    about_us: str
    mission: str
    updated_at: datetime | None


class PublicContentUpdate(BaseModel):
    about_us: str | None = Field(
        None, min_length=1, max_length=20000,
        examples=["PawGuard rescues, rehabilitates and rehomes street dogs."],
    )
    mission: str | None = Field(
        None, min_length=1, max_length=20000,
        examples=["To give every stray dog a safe home and a second chance."],
    )
