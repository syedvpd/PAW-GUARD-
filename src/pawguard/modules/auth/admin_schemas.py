"""Pydantic DTOs for admin endpoints (user provisioning, role/permission management)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# ── Role ─────────────────────────────────────────────────────────────────────

class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None
    permission_codes: list[str] = []


class RoleUpdateRequest(BaseModel):
    description: str | None = None
    permission_codes: list[str] | None = None


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
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── User (admin) ─────────────────────────────────────────────────────────────

class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = None
    role_names: list[str] = []


class AdminUserUpdateRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    role_names: list[str] | None = None


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    roles: list[str]
    created_at: datetime
    updated_at: datetime

    @field_validator("roles", mode="before")
    @classmethod
    def serialize_roles(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [r.name if hasattr(r, "name") else str(r) for r in v]
        return list(v) if isinstance(v, (list, tuple)) else []

    model_config = {"from_attributes": True}
