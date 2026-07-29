"""Pydantic DTOs for admin endpoints (user provisioning, role/permission management)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

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

    model_config = {"from_attributes": True}
