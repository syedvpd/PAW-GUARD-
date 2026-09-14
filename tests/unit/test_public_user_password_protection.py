"""Unit and security tests for Public User Password Protection against administrative changes."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pawguard.core.exceptions import ForbiddenError
from pawguard.core.security import AccessTokenClaims
from pawguard.modules.auth.admin_router import admin_router
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.auth.repository import (
    PermissionRepository,
    RoleRepository,
    UserRepository,
    UserRoleRepository,
)
from pawguard.modules.auth.service import AdminService
from pawguard.services.audit_service import AuditService


def _create_role(name: str) -> Role:
    now = datetime.now(UTC)
    return Role(
        id=uuid.uuid4(),
        name=name,
        description=f"{name} role",
        is_system=True,
        created_at=now,
        updated_at=now,
    )


def _create_user(email: str, role_names: list[str]) -> User:
    now = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        email=email.lower(),
        full_name="Test User",
        phone="+1555123456",
        hashed_password="hashed_pass_sample",
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
        created_at=now,
        updated_at=now,
    )
    user.roles = [_create_role(r) for r in role_names]
    return user


class TestPublicUserPasswordProtectionService:
    @pytest.fixture
    def mock_user_repo(self):
        repo = AsyncMock(spec=UserRepository)
        repo._session = AsyncMock()
        repo._session.flush = AsyncMock()
        repo._session.refresh = AsyncMock()
        return repo

    @pytest.fixture
    def mock_role_repo(self):
        return AsyncMock(spec=RoleRepository)

    @pytest.fixture
    def mock_perm_repo(self):
        return AsyncMock(spec=PermissionRepository)

    @pytest.fixture
    def mock_user_role_repo(self):
        return AsyncMock(spec=UserRoleRepository)

    @pytest.fixture
    def mock_audit(self):
        audit = AsyncMock(spec=AuditService)
        audit.record = AsyncMock()
        return audit

    @pytest.fixture
    def admin_service(
        self,
        mock_user_repo,
        mock_role_repo,
        mock_perm_repo,
        mock_user_role_repo,
        mock_audit,
    ):
        return AdminService(
            user_repo=mock_user_repo,
            role_repo=mock_role_repo,
            permission_repo=mock_perm_repo,
            user_role_repo=mock_user_role_repo,
            audit_service=mock_audit,
        )

    @pytest.mark.asyncio
    async def test_admin_cannot_update_general_public_password(self, admin_service, mock_user_repo):
        """1. Super Admin attempting to update General Public User password is rejected with 403."""
        public_user = _create_user("citizen@example.com", ["general_public"])
        mock_user_repo.get_by_id.return_value = public_user

        with pytest.raises(
            ForbiddenError, match="General public user passwords cannot be administratively changed"
        ):
            await admin_service.update_user(
                public_user.id,
                password="NewAdministrativePassword123!",
                actor_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_admin_cannot_update_general_public_user_role_password(
        self, admin_service, mock_user_repo
    ):
        """2. Super Admin attempting to update password for user with general_public_user role is rejected."""
        public_user = _create_user("app_user@example.com", ["general_public_user"])
        mock_user_repo.get_by_id.return_value = public_user

        with pytest.raises(
            ForbiddenError, match="General public user passwords cannot be administratively changed"
        ):
            await admin_service.update_user(
                public_user.id,
                password="NewAdministrativePassword123!",
                actor_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_admin_cannot_assign_public_role_and_password_together(
        self, admin_service, mock_user_repo
    ):
        """3. Super Admin cannot assign general_public role and set password simultaneously."""
        user = _create_user("target@example.com", [])
        mock_user_repo.get_by_id.return_value = user

        with pytest.raises(
            ForbiddenError, match="General public user passwords cannot be administratively changed"
        ):
            await admin_service.update_user(
                user.id,
                role_names=["general_public"],
                password="NewAdministrativePassword123!",
                actor_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_admin_can_update_public_user_non_password_profile_fields(
        self, admin_service, mock_user_repo
    ):
        """4. Super Admin can update permitted non-password profile fields of General Public User."""
        public_user = _create_user("citizen@example.com", ["general_public"])
        mock_user_repo.get_by_id.return_value = public_user

        updated = await admin_service.update_user(
            public_user.id,
            full_name="Citizen Updated Name",
            phone="+91-9876543210",
            is_active=True,
            can_drive=True,
            actor_id=uuid.uuid4(),
        )

        assert updated.full_name == "Citizen Updated Name"
        assert updated.phone == "+91-9876543210"
        assert updated.can_drive is True

    @pytest.mark.asyncio
    async def test_admin_can_manage_authorized_staff_passwords(self, admin_service, mock_user_repo):
        """5. Super Admin can manage password for authorized Admin Portal roles (e.g. shelter_manager)."""
        staff_user = _create_user("shelter.manager@pawguard.org", ["shelter_manager"])
        mock_user_repo.get_by_id.return_value = staff_user

        with patch(
            "pawguard.modules.auth.service.hash_password", return_value="new_hashed_password"
        ):
            updated = await admin_service.update_user(
                staff_user.id,
                password="NewStaffPassword123!",
                actor_id=uuid.uuid4(),
            )
            assert updated.hashed_password == "new_hashed_password"

    @pytest.mark.asyncio
    async def test_admin_cannot_restore_and_reset_public_user_password(
        self, admin_service, mock_user_repo
    ):
        """6. Super Admin cannot restore_and_reset password for General Public User."""
        public_user = _create_user("citizen@example.com", ["general_public"])
        mock_user_repo.get_by_email_any.return_value = public_user

        with pytest.raises(
            ForbiddenError, match="General public user passwords cannot be administratively changed"
        ):
            await admin_service.restore_and_reset_password(
                email="citizen@example.com",
                password="NewAdministrativePassword123!",
                actor_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_admin_can_restore_and_reset_staff_password(self, admin_service, mock_user_repo):
        """7. Super Admin can restore_and_reset password for authorized staff accounts."""
        staff_user = _create_user("vet@pawguard.org", ["veterinarian"])
        mock_user_repo.get_by_email_any.return_value = staff_user

        with patch(
            "pawguard.modules.auth.service.hash_password", return_value="new_vet_hashed_password"
        ):
            restored = await admin_service.restore_and_reset_password(
                email="vet@pawguard.org",
                password="NewVetPassword123!",
                actor_id=uuid.uuid4(),
            )
            assert restored.hashed_password == "new_vet_hashed_password"
            assert restored.is_active is True


class TestPublicUserPasswordProtectionRouter:
    @pytest.fixture
    def test_app(self):
        from pawguard.core.exceptions import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(admin_router, prefix="/api/v1")
        return app

    @pytest.fixture
    def mock_super_admin(self):
        now = datetime.now(UTC)
        admin_role = Role(
            id=uuid.uuid4(),
            name="super_admin",
            description="Super Admin",
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
        admin_role.permissions = [perm]

        user = User(
            id=uuid.uuid4(),
            email="admin@pawguard.org",
            full_name="Super Admin",
            phone="+1555123456",
            hashed_password="hashed_pass",
            is_active=True,
            is_verified=True,
            mfa_enabled=False,
            created_at=now,
            updated_at=now,
        )
        user.roles = [admin_role]

        claims = AccessTokenClaims(
            user_id=user.id,
            session_id=uuid.uuid4(),
            roles=["super_admin"],
            jti=str(uuid.uuid4()),
            expires_at=now,
        )
        return CurrentUser(user=user, claims=claims, db=AsyncMock(), redis=AsyncMock())

    @pytest.mark.asyncio
    async def test_put_admin_users_endpoint_rejects_public_password_update(
        self, test_app, mock_super_admin
    ):
        """8. Direct API call to PUT /api/v1/admin/users/{user_id} with password returns 403 Forbidden for public user."""
        public_user = _create_user("citizen@example.com", ["general_public"])

        mock_service = AsyncMock(spec=AdminService)
        mock_service.update_user.side_effect = ForbiddenError(
            "General public user passwords cannot be administratively changed."
        )

        test_app.dependency_overrides[get_current_user] = lambda: mock_super_admin
        from pawguard.modules.auth.admin_router import _get_admin_service

        test_app.dependency_overrides[_get_admin_service] = lambda: mock_service

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.put(
                f"/api/v1/admin/users/{public_user.id}",
                json={
                    "password": "HackerPassword123!",
                },
            )

        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "AUTHORIZATION_FAILED"
        assert (
            "General public user passwords cannot be administratively changed."
            in data["error"]["message"]
        )

    @pytest.mark.asyncio
    async def test_put_admin_users_endpoint_allows_public_profile_update(
        self, test_app, mock_super_admin
    ):
        """9. Direct API call to PUT /api/v1/admin/users/{user_id} without password succeeds for public user."""
        public_user = _create_user("citizen@example.com", ["general_public"])
        public_user.full_name = "Updated Citizen Name"

        mock_service = AsyncMock(spec=AdminService)
        mock_service.update_user.return_value = public_user

        test_app.dependency_overrides[get_current_user] = lambda: mock_super_admin
        from pawguard.modules.auth.admin_router import _get_admin_service

        test_app.dependency_overrides[_get_admin_service] = lambda: mock_service

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.put(
                f"/api/v1/admin/users/{public_user.id}",
                json={
                    "full_name": "Updated Citizen Name",
                    "phone": "+91-9876543210",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["full_name"] == "Updated Citizen Name"
