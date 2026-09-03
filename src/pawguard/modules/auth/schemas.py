"""Pydantic request/response DTOs for the auth module."""

import re
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

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


NAME_REGEX = re.compile(r"^[a-zA-Z\s\.\'\-]+$")
PHONE_REGEX = re.compile(r"^\+?[1-9]\d{6,14}$")
INDIAN_PHONE_REGEX = re.compile(r"^\+91[6-9]\d{9}$")


class DeviceContext(BaseModel):
    device_id: str | None = Field(None, examples=["a1b2c3d4-device-001"])
    device_name: str | None = Field(None, examples=["Jane's iPhone 15"])
    device_type: DeviceType = DeviceType.UNKNOWN


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., examples=["jane.doe@example.com"])
    password: str = Field(..., examples=["StrongP@ssw0rd"])
    first_name: str | None = Field(None, examples=["Jane"])
    last_name: str | None = Field(None, examples=["Doe"])
    full_name: str = Field(default="", min_length=0, max_length=255, examples=["Jane Doe"])
    phone: str | None = Field(None, examples=["+919876543210"])

    @model_validator(mode="before")
    @classmethod
    def _coerce_names(cls, data: Any) -> Any:
        if isinstance(data, dict):
            fn = data.get("first_name")
            ln = data.get("last_name")
            full = data.get("full_name")
            if not full and fn:
                data["full_name"] = f"{fn} {ln}".strip() if ln else fn.strip()
        return data

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        val = value.strip()
        if not val:
            raise ValueError("Full name cannot be empty.")
        if any(char.isdigit() for char in val):
            raise ValueError("Full name must contain only alphabetic characters, not numbers.")
        if not NAME_REGEX.match(val):
            raise ValueError("Full name contains invalid characters.")
        return val

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            val = re.sub(r"[\s\-()]", "", v.strip())
            if not val:
                return None
            if val.startswith("+91") and not INDIAN_PHONE_REGEX.match(val):
                raise ValueError(
                    "Indian mobile number (+91) must have exactly 10 digits without special characters."
                )
            if not PHONE_REGEX.match(val):
                raise ValueError("Invalid phone number format.")
            return val
        return v


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

    @model_validator(mode="after")
    def password_must_be_different(self) -> "ChangePasswordRequest":
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from current password.")
        return self


class CreatePasswordRequest(BaseModel):
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


class MFADisableRequest(BaseModel):
    password: str | None = Field(None, examples=["CurrentP@ssw0rd"])
    totp_code: str | None = Field(None, min_length=6, max_length=6, examples=["482913"])

    @model_validator(mode="after")
    def at_least_one_credential(self) -> "MFADisableRequest":
        if self.password is None and self.totp_code is None:
            raise ValueError("Provide either your current password or a valid TOTP code.")
        return self


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(None, examples=["Jane Doe"])
    phone: str | None = Field(None, examples=["+1-555-0100"])
    profile_picture_url: str | None = Field(
        None, alias="avatar_url", examples=["https://example.com/avatar.jpg"]
    )
    date_of_birth: date | str | None = Field(None, alias="dob", examples=["1995-05-15"])
    gender: str | None = Field(None, examples=["female"])
    address_line: str | None = Field(None, alias="address", examples=["123 Rescue Way"])
    city: str | None = Field(None, examples=["Sector 4"])
    state: str | None = Field(None, examples=["Telangana"])
    country: str | None = Field(None, examples=["India"])
    postal_code: str | None = Field(None, alias="pin_code", examples=["500081"])
    push_notifications_enabled: bool | None = Field(
        None, alias="push_notifications", examples=[True]
    )
    fcm_token: str | None = Field(
        None,
        description="FCM device token for push notifications.",
    )

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }

    @field_validator("full_name", mode="before")
    @classmethod
    def validate_full_name(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                raise ValueError("Full name cannot be empty.")
            return v_str
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            if not val:
                return None
            if not PHONE_REGEX.match(val):
                raise ValueError("Invalid phone number format.")
            return val
        return v

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_dob(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                return None
            try:
                return date.fromisoformat(v_str)
            except ValueError:
                raise ValueError("Invalid date_of_birth format. Use YYYY-MM-DD.") from None
        return v

    @model_validator(mode="before")
    @classmethod
    def handle_aliases_and_extra_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "postal_code" not in data and "pin_code" in data:
                data["postal_code"] = data["pin_code"]
            elif "postal_code" not in data and "zip_code" in data:
                data["postal_code"] = data["zip_code"]
            if "profile_picture_url" not in data and "avatar_url" in data:
                data["profile_picture_url"] = data["avatar_url"]
            if "push_notifications_enabled" not in data and "push_notifications" in data:
                data["push_notifications_enabled"] = data["push_notifications"]
            if "address_line" not in data and "address" in data:
                data["address_line"] = data["address"]
            if "date_of_birth" not in data and "dob" in data:
                data["date_of_birth"] = data["dob"]
        return data

    @model_validator(mode="after")
    def at_least_one_field_provided(self) -> "UserProfileUpdate":
        fields = [
            self.full_name,
            self.phone,
            self.profile_picture_url,
            self.date_of_birth,
            self.gender,
            self.address_line,
            self.city,
            self.state,
            self.country,
            self.postal_code,
            self.push_notifications_enabled,
        ]
        if all(f is None for f in fields):
            raise ValueError("At least one field must be provided for profile update.")
        return self


class UserProfile(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None = None
    profile_picture_url: str | None = None
    avatar_url: str | None = None
    date_of_birth: date | str | None = None
    gender: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    pin_code: str | None = None
    zip_code: str | None = None
    push_notifications_enabled: bool = True
    push_notifications: bool = True
    is_verified: bool
    mfa_enabled: bool
    can_drive: bool = False
    has_password: bool = True
    auth_provider: str | None = None
    roles: list[str]

    @field_validator("roles", mode="before")
    @classmethod
    def serialize_roles(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [r.name if hasattr(r, "name") else str(r) for r in v]
        return list(v) if isinstance(v, (list, tuple)) else []

    @model_validator(mode="after")
    def populate_alias_fields(self) -> "UserProfile":
        if self.avatar_url is None:
            self.avatar_url = self.profile_picture_url
        if self.pin_code is None:
            self.pin_code = self.postal_code
        if self.zip_code is None:
            self.zip_code = self.postal_code
        self.push_notifications = self.push_notifications_enabled
        return self

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


class UserSummaryResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None = None
    profile_picture_url: str | None = None
    role: str | None = None

    model_config = ConfigDict(from_attributes=True)
