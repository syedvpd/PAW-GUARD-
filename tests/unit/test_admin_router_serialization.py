"""Unit tests for Admin router endpoint serialization contracts."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pawguard.modules.auth.admin_router import admin_router
from pawguard.modules.auth.dependencies import get_current_user
from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.auth.rbac import require_permission


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(admin_router, prefix="/api/v1")
    return app


from pawguard.core.security import AccessTokenClaims
from pawguard.modules.auth.dependencies import CurrentUser


@pytest.fixture
def mock_admin_user():
    now = datetime.now(UTC)
    role = Role(
        id=uuid.uuid4(),
        name="super_admin",
        description="Super Administrator",
        is_system=True,
        created_at=now,
        updated_at=now,
    )
    perm = Permission(
        id=uuid.uuid4(),
        code="system:admin",
        description="System Admin",
        created_at=now,
        updated_at=now,
    )
    role.permissions = [perm]

    user = User(
        id=uuid.uuid4(),
        email="admin@pawguard.org",
        full_name="Super Admin",
        phone="+1555123456",
        hashed_password="hashed_pass_sample",
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
        created_at=now,
        updated_at=now,
    )
    user.roles = [role]
    claims = AccessTokenClaims(
        user_id=user.id,
        session_id=uuid.uuid4(),
        roles=["super_admin"],
        jti=str(uuid.uuid4()),
        expires_at=now,
    )
    return CurrentUser(
        user=user,
        claims=claims,
        db=AsyncMock(),
        redis=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_admin_list_users_serialization(test_app, mock_admin_user):
    now = datetime.now(UTC)
    role = Role(
        id=uuid.uuid4(),
        name="shelter_manager",
        description="Shelter Manager",
        is_system=False,
        created_at=now,
        updated_at=now,
    )
    user = User(
        id=uuid.uuid4(),
        email="staff@pawguard.org",
        full_name="Staff Member",
        phone="+1555987654",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
        created_at=now,
        updated_at=now,
    )
    user.roles = [role]

    mock_service = AsyncMock()
    mock_service.list_users.return_value = [user, mock_admin_user.user]

    # Override dependencies
    test_app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    test_app.dependency_overrides[require_permission("system:admin")] = lambda: mock_admin_user
    from pawguard.modules.auth.admin_router import _get_admin_service

    test_app.dependency_overrides[_get_admin_service] = lambda: mock_service

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]) == 2
        assert data["data"][0]["email"] == "staff@pawguard.org"
        assert data["data"][0]["roles"] == ["shelter_manager"]
        assert data["data"][1]["email"] == "admin@pawguard.org"
        assert data["data"][1]["roles"] == ["super_admin"]


@pytest.mark.asyncio
async def test_admin_list_roles_serialization(test_app, mock_admin_user):
    now = datetime.now(UTC)
    perm = Permission(
        id=uuid.uuid4(),
        code="rescue:read",
        description="Read rescue cases",
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=uuid.uuid4(),
        name="rescue_driver",
        description="Rescue Driver Role",
        is_system=False,
        created_at=now,
        updated_at=now,
    )
    role.permissions = [perm]

    mock_service = AsyncMock()
    mock_service.list_roles.return_value = [role]

    test_app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    test_app.dependency_overrides[require_permission("system:admin")] = lambda: mock_admin_user
    from pawguard.modules.auth.admin_router import _get_admin_service

    test_app.dependency_overrides[_get_admin_service] = lambda: mock_service

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "rescue_driver"
        assert data["data"][0]["permission_codes"] == ["rescue:read"]


@pytest.mark.asyncio
async def test_admin_get_single_user_and_role_serialization(test_app, mock_admin_user):
    now = datetime.now(UTC)
    role = Role(
        id=uuid.uuid4(),
        name="finance_officer",
        description="Finance Officer Role",
        is_system=False,
        created_at=now,
        updated_at=now,
    )
    role.permissions = []

    user = User(
        id=uuid.uuid4(),
        email="finance@pawguard.org",
        full_name="Finance Officer",
        phone=None,
        hashed_password="hash",
        is_active=True,
        is_verified=True,
        mfa_enabled=True,
        created_at=now,
        updated_at=now,
    )
    user.roles = [role]

    mock_service = AsyncMock()
    mock_service.get_user.return_value = user
    mock_service.get_role.return_value = role

    test_app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    test_app.dependency_overrides[require_permission("system:admin")] = lambda: mock_admin_user
    from pawguard.modules.auth.admin_router import _get_admin_service

    test_app.dependency_overrides[_get_admin_service] = lambda: mock_service

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_user = await client.get(f"/api/v1/admin/users/{user.id}")
        assert resp_user.status_code == 200
        user_data = resp_user.json()
        assert user_data["success"] is True
        assert user_data["data"]["email"] == "finance@pawguard.org"
        assert user_data["data"]["mfa_enabled"] is True

        resp_role = await client.get(f"/api/v1/admin/roles/{role.id}")
        assert resp_role.status_code == 200
        role_data = resp_role.json()
        assert role_data["success"] is True
        assert role_data["data"]["name"] == "finance_officer"
