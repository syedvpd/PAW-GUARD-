"""Pydantic request/response DTOs for the auth module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from pawguard.core.constants import DeviceType

PASSWORD_MIN_LENGTH = 10


def _validate_password_strength(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must contain an uppercase letter.")
    if not any(c.islower() for c in value):
        raise ValueError("Password must contain a lowercase letter.")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain a digit.")
    return value


class DeviceContext(BaseModel):
    device_id: str | None = Field(None, examples=["a1b2c3d4-device-001"])
    device_name: str | None = Field(None, examples=["Jane's iPhone 15"])
    device_type: DeviceType = DeviceType.UNKNOWN


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., examples=["jane.doe@example.com"])
    password: str = Field(..., examples=["StrongP@ssw0rd"])
    full_name: str = Field(min_length=1, max_length=255, examples=["Jane Doe"])
    phone: str | None = Field(None, examples=["+1-555-0100"])

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., examples=["jane.doe@example.com"])
    password: str = Field(..., examples=["StrongP@ssw0rd"])
    device: DeviceContext = DeviceContext()


class LoginResponse(BaseModel):
    """Populated when no MFA step is required."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int
    user: "UserProfile"


class MFARequiredResponse(BaseModel):
    mfa_required: bool = True
    pre_auth_token: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(None, examples=["dGhpc2lzYXJlZnJlc2h0b2tlbg=="])


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(None, examples=["dGhpc2lzYXJlZnJlc2h0b2tlbg=="])


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., examples=["OldP@ssw0rd"])
    new_password: str = Field(..., examples=["NewStr0ng!Pass"])

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(..., examples=["jane.doe@example.com"])


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., examples=["a1b2c3d4e5f6-reset-token"])
    new_password: str = Field(..., examples=["NewStr0ng!Pass"])

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(..., examples=["a1b2c3d4e5f6-verify-token"])


class MFAEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MFAVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, examples=["482913"])


class MFALoginVerifyRequest(BaseModel):
    pre_auth_token: str = Field(..., examples=["a1b2c3d4e5f6-pre-auth"])
    code: str = Field(min_length=6, max_length=6, examples=["482913"])
    device: DeviceContext = DeviceContext()


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(None, examples=["Jane Doe"])
    phone: str | None = Field(None, examples=["+1-555-0100"])


class UserProfile(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None = None
    is_verified: bool
    mfa_enabled: bool
    roles: list[str]

    @field_validator("roles", mode="before")
    @classmethod
    def serialize_roles(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [r.name if hasattr(r, "name") else str(r) for r in v]
        return list(v) if isinstance(v, (list, tuple)) else []

    model_config = {"from_attributes": True}


class SessionInfo(BaseModel):
    id: uuid.UUID
    device_name: str | None
    device_type: DeviceType
    ip_address: str | None
    is_active: bool
    last_used_at: datetime
    created_at: datetime
    is_current: bool = False

    model_config = {"from_attributes": True}


# ── OAuth / Social Login ──────────────────────────────────────────────────────


class OAuthLoginRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32, examples=["google"])
    provider_token: str = Field(..., examples=["ya29.a0AfH6SMC...token"])
    device: DeviceContext = DeviceContext()


class OAuthCallbackResponse(BaseModel):
    """Returned when a new account is created via OAuth."""

    is_new_user: bool = False


class OAuthAccountInfo(BaseModel):
    id: uuid.UUID
    provider: str
    provider_user_id: str
    provider_email: str | None
    display_name: str | None
    picture_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OAuthLinkRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32, examples=["google"])
    provider_token: str = Field(..., examples=["ya29.a0AfH6SMC...token"])
