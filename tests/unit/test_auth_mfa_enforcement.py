"""Unit tests for mandatory MFA enforcement on admin accounts.

Admins (users holding the `system:admin` permission) must always complete an
MFA challenge at login - even before they have enrolled - and can never
disable MFA. This closes the "admin-mandatory MFA enforcement" gap.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from pawguard.core.constants import DeviceType
from pawguard.core.security import create_pre_auth_token
from pawguard.modules.auth.exceptions import MFADisableNotAllowedError, MFARequiredError
from pawguard.modules.auth.models import MFADevice, Permission, Role, User, UserSession
from pawguard.modules.auth.schemas import DeviceContext, MFADisableRequest
from pawguard.modules.auth.service import AuthenticatedTokens, AuthService, RequestContext


def _make_service(**overrides: object) -> AuthService:
    kwargs = dict(
        user_repo=AsyncMock(),
        session_repo=AsyncMock(),
        refresh_token_repo=AsyncMock(),
        mfa_repo=AsyncMock(),
        password_reset_repo=AsyncMock(),
        email_verification_repo=AsyncMock(),
        oauth_account_repo=AsyncMock(),
        audit_service=AsyncMock(),
    )
    kwargs.update(overrides)
    svc = AuthService(**kwargs)  # type: ignore[arg-type]
    svc._settings.mfa_mandatory_for_admins = True
    return svc


def _admin_user(**kw: object) -> User:
    mfa_enabled = kw.pop("mfa_enabled", False)
    role = Role(name="Super Admin", description="System administrator", is_system=True)
    role.permissions = [Permission(code="system:admin")]
    user = User(
        email="admin@example.com",
        hashed_password="x",
        full_name="Admin User",
        is_active=True,
        mfa_enabled=mfa_enabled,
        **kw,
    )
    user.id = uuid.uuid4()
    user.roles = [role]
    return user


def _regular_user(**kw: object) -> User:
    mfa_enabled = kw.pop("mfa_enabled", False)
    hashed_password = kw.pop("hashed_password", "x")
    user = User(
        email="user@example.com",
        hashed_password=hashed_password,
        full_name="Regular User",
        is_active=True,
        mfa_enabled=mfa_enabled,
        **kw,
    )
    user.id = uuid.uuid4()
    user.roles = []
    return user


def _device_context() -> DeviceContext:
    return DeviceContext(
        device_id="device-1", device_name="pytest", device_type=DeviceType.IOS
    )


def _ctx() -> RequestContext:
    return RequestContext(ip_address="127.0.0.1", user_agent="pytest")


def _session(user_id: uuid.UUID) -> UserSession:
    return UserSession(
        id=uuid.uuid4(),
        user_id=user_id,
        is_active=True,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


class TestAdminMfaLoginEnforcement:
    @pytest.mark.asyncio
    @patch("pawguard.modules.auth.service.verify_password", return_value=True)
    @patch("pawguard.modules.auth.service.needs_rehash", return_value=False)
    async def test_login_admin_without_mfa_still_requires_mfa_step(
        self, mock_needs_rehash, mock_verify
    ):
        """An admin with MFA not yet enabled must still hit the MFA challenge
        at login (mandatory enforcement), not get straight tokens."""
        admin = _admin_user()
        user_repo = AsyncMock()
        user_repo.get_by_email.return_value = admin
        session = _session(admin.id)
        session_repo = AsyncMock()
        session_repo.create.return_value = session
        svc = _make_service(user_repo=user_repo, session_repo=session_repo)

        result = await svc.login(
            email="admin@example.com",
            password="pw",
            device=_device_context(),
            ctx=_ctx(),
        )

        assert isinstance(result, str)  # pre-auth token, not AuthenticatedTokens
        assert svc._refresh_tokens.create.call_count == 0  # no tokens issued yet

    @pytest.mark.asyncio
    @patch("pawguard.modules.auth.service.verify_password", return_value=True)
    @patch("pawguard.modules.auth.service.needs_rehash", return_value=False)
    async def test_login_admin_with_mfa_requires_mfa_step(
        self, mock_needs_rehash, mock_verify
    ):
        admin = _admin_user(mfa_enabled=True)
        user_repo = AsyncMock()
        user_repo.get_by_email.return_value = admin
        session = _session(admin.id)
        session_repo = AsyncMock()
        session_repo.create.return_value = session
        svc = _make_service(user_repo=user_repo, session_repo=session_repo)

        result = await svc.login(
            email="admin@example.com",
            password="pw",
            device=_device_context(),
            ctx=_ctx(),
        )

        assert isinstance(result, str)

    @pytest.mark.asyncio
    @patch("pawguard.modules.auth.service.verify_password", return_value=True)
    @patch("pawguard.modules.auth.service.needs_rehash", return_value=False)
    async def test_login_regular_user_without_mfa_issues_tokens(
        self, mock_needs_rehash, mock_verify
    ):
        """Non-admin users without MFA keep the existing straight-token login."""
        user = _regular_user()
        user_repo = AsyncMock()
        user_repo.get_by_email.return_value = user
        session = _session(user.id)
        session_repo = AsyncMock()
        session_repo.create.return_value = session
        svc = _make_service(user_repo=user_repo, session_repo=session_repo)

        result = await svc.login(
            email="user@example.com",
            password="pw",
            device=_device_context(),
            ctx=_ctx(),
        )

        assert isinstance(result, AuthenticatedTokens)
        assert result.access_token
        assert svc._refresh_tokens.create.call_count == 1

    @pytest.mark.asyncio
    async def test_verify_mfa_login_admin_not_enrolled_raises_mfa_required(self):
        """An admin without an enrolled device cannot complete login via the
        MFA step; they are told to enroll first."""
        admin = _admin_user()
        user_repo = AsyncMock()
        user_repo.get_by_id.return_value = admin
        session = _session(admin.id)
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = session
        mfa_repo = AsyncMock()
        mfa_repo.get_for_user.return_value = None
        svc = _make_service(
            user_repo=user_repo, session_repo=session_repo, mfa_repo=mfa_repo
        )
        pre_token = create_pre_auth_token(user_id=admin.id, session_id=session.id)

        with pytest.raises(MFARequiredError, match="enroll in MFA"):
            await svc.verify_mfa_login(
                pre_auth_token=pre_token,
                code="123456",
                device=_device_context(),
                ctx=_ctx(),
            )


class TestAdminMfaDisableEnforcement:
    @pytest.mark.asyncio
    async def test_disable_mfa_blocked_for_admin(self):
        svc = _make_service()
        admin = _admin_user(mfa_enabled=True)

        with pytest.raises(MFADisableNotAllowedError, match="keep MFA enabled"):
            await svc.disable_mfa(
                user=admin,
                payload=MFADisableRequest(password="Whatever1!"),
                ctx=_ctx(),
            )

        assert admin.mfa_enabled is True

    @pytest.mark.asyncio
    async def test_disable_mfa_allowed_for_regular_user(self):
        user = _regular_user(
            mfa_enabled=True,
            hashed_password=(
                "$argon2id$v=19$m=19456,t=2,p=1$JoRb+Y2/MpzJ6oPcWhcnXQ"
                "$A6Q5RTBxi8gO4/TycFnK1GZU/GFnC2aGz9yEfVLS9mM"
            ),
        )
        device = MFADevice(
            user_id=user.id,
            device_type="totp",
            secret_encrypted="placeholder",
            is_verified=True,
        )
        mfa_repo = AsyncMock()
        mfa_repo.get_for_user.return_value = device
        svc = _make_service(mfa_repo=mfa_repo)

        await svc.disable_mfa(
            user=user,
            payload=MFADisableRequest(password="CorrectPassword1!"),
            ctx=_ctx(),
        )

        assert user.mfa_enabled is False
        assert device.is_verified is False


class TestIsAdmin:
    def test_is_admin_true_for_system_admin_permission(self):
        assert AuthService._is_admin(_admin_user()) is True

    def test_is_admin_false_for_regular_user(self):
        assert AuthService._is_admin(_regular_user()) is False

    def test_is_admin_false_without_system_admin_permission(self):
        role = Role(name="Staff", is_system=False)
        role.permissions = [Permission(code="rescue:verify")]
        user = User(
            email="staff@example.com",
            hashed_password="x",
            full_name="Staff",
            is_active=True,
        )
        user.roles = [role]
        assert AuthService._is_admin(user) is False
