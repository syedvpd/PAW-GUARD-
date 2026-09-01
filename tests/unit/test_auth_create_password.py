"""Unit tests for OAuth user initial password creation."""

import uuid
from unittest.mock import AsyncMock

import pytest

from pawguard.core.security import verify_password
from pawguard.modules.auth.models import User
from pawguard.modules.auth.repository import UserRepository
from pawguard.modules.auth.service import AuthService, RequestContext
from pawguard.services.audit_service import AuditService


@pytest.fixture
def mock_users():
    repo = AsyncMock(spec=UserRepository)
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def mock_audit():
    return AsyncMock(spec=AuditService)


@pytest.fixture
def auth_service(mock_users, mock_audit):
    return AuthService(
        user_repo=mock_users,
        session_repo=AsyncMock(),
        refresh_token_repo=AsyncMock(),
        mfa_repo=AsyncMock(),
        password_reset_repo=AsyncMock(),
        email_verification_repo=AsyncMock(),
        oauth_account_repo=AsyncMock(),
        audit_service=mock_audit,
    )


@pytest.mark.asyncio
async def test_create_password_sets_usable_hash(auth_service, mock_audit):
    user = User(
        id=uuid.uuid4(),
        email="google.user@example.com",
        full_name="Google User",
        hashed_password="",
        is_active=True,
    )
    ctx = RequestContext(ip_address="127.0.0.1", user_agent="TestBrowser")

    await auth_service.create_password(
        user=user,
        new_password="NewStr0ng!Password123",
        ctx=ctx,
    )

    assert user.hashed_password != ""
    assert verify_password("NewStr0ng!Password123", user.hashed_password) is True
    mock_audit.record.assert_awaited_once()
