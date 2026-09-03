"""Pydantic DTOs for admin endpoints (user provisioning, role/permission management)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# ── Role ─────────────────────────────────────────────────────────────────────


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, examples=["event_coordinator"])
    description: str | None = Field(None, examples=["Plans and runs community adoption events."])
    permission_codes: list[str] = Field(default=[], examples=[["adoption:read", "public:read"]])

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v_stripped = v.strip()
        if not v_stripped:
            raise ValueError("Role name cannot be empty or whitespace-only")
        return v_stripped


class RoleUpdateRequest(BaseModel):
    description: str | None = Field(None, examples=["Updated role description."])
    permission_codes: list[str] | None = Field(
        None, examples=[["adoption:read", "adoption:process"]]
    )


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    permission_codes: list[str] = []
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _inject_permission_codes(cls, data: Any) -> Any:
        # Role.permissions is an ORM relationship, not an attribute literally
        # named permission_codes - from_attributes alone silently falls back
        # to the [] default here, so every role would appear permission-less.
        if hasattr(data, "permissions") and not isinstance(data, dict):
            return {
                "id": data.id,
                "name": data.name,
                "description": data.description,
                "is_system": data.is_system,
                "permission_codes": [p.code for p in data.permissions],
                "created_at": data.created_at,
            }
        return data

    model_config = {"from_attributes": True}


class PermissionResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str = ""
    description: str | None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _populate_name(cls, data: Any) -> Any:
        if hasattr(data, "code") and not isinstance(data, dict):
            return {
                "id": data.id,
                "code": data.code,
                "name": getattr(data, "name", None) or data.code,
                "description": data.description,
                "created_at": data.created_at,
            }
        elif isinstance(data, dict) and "code" in data:
            data.setdefault("name", data.get("name") or data["code"])
        return data

    model_config = {"from_attributes": True}


# ── User (admin) ─────────────────────────────────────────────────────────────


class AdminUserCreateRequest(BaseModel):
    email: EmailStr = Field(..., examples=["new.staff@pawguard.com"])
    password: str = Field(min_length=10, examples=["StrongP@ssw0rd"])
    full_name: str = Field(min_length=1, max_length=255, examples=["Alex Rivera"])
    phone: str | None = Field(None, examples=["+1-555-0100"])
    role_names: list[str] = Field(default=[], examples=[["shelter_manager"]])
    can_drive: bool = Field(default=False, examples=[True])


class AdminRestorePasswordRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, examples=["PawGuard@2026"])


class AdminUserUpdateRequest(BaseModel):
    full_name: str | None = Field(None, examples=["Alex Rivera"])
    phone: str | None = Field(None, examples=["+1-555-0100"])
    is_active: bool | None = Field(None, examples=[True])
    can_drive: bool | None = Field(None, examples=[True])
    role_names: list[str] | None = Field(None, examples=[["shelter_manager"]])
    password: str | None = Field(None, min_length=10, examples=["StrongP@ssw0rd"])


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    can_drive: bool = False
    roles: list[str]
    direct_permissions: list[str] = []
    created_at: datetime
    updated_at: datetime

    @field_validator("roles", mode="before")
    @classmethod
    def serialize_roles(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [r.name if hasattr(r, "name") else str(r) for r in v]
        return list(v) if isinstance(v, (list, tuple)) else []

    @field_validator("direct_permissions", mode="before")
    @classmethod
    def serialize_direct_permissions(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [p.code if hasattr(p, "code") else str(p) for p in v]
        return list(v) if isinstance(v, (list, tuple)) else []

    model_config = {"from_attributes": True}


# ── User Permission Overrides ────────────────────────────────────────────────


class UserPermissionGrantRequest(BaseModel):
    permission_codes: list[str] = Field(
        ...,
        min_length=1,
        examples=[["finance:export", "reports:export_pdf"]],
        description="Permission codes to grant directly to the user.",
    )


class UserPermissionRevokeRequest(BaseModel):
    permission_code: str = Field(
        ...,
        examples=["finance:export"],
        description="Permission code to revoke from the user.",
    )


class UserPermissionResponse(BaseModel):
    user_id: uuid.UUID
    direct_permissions: list[str]
    granted_at: dict[str, datetime] = {}

    model_config = ConfigDict(from_attributes=True)
