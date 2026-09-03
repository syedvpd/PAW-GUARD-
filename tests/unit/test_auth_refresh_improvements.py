"""Unit tests for auth token refresh, cookie handling, and grace period concurrency."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from pawguard.core.security import hash_opaque_token
from pawguard.modules.auth.models import RefreshToken, User, UserSession
from pawguard.modules.auth.router import _to_login_response
from pawguard.modules.auth.schemas import RefreshRequest
from pawguard.modules.auth.service import AuthenticatedTokens, AuthService, RequestContext


def test_refresh_request_schema_supports_camel_case_and_empty():
    # Empty payload
    r1 = RefreshRequest()
    assert r1.refresh_token is None

    # camelCase payload from JavaScript/Next.js client
    r2 = RefreshRequest.model_validate({"refreshToken": "token-123"})
    assert r2.refresh_token == "token-123"

    # snake_case payload
    r3 = RefreshRequest.model_validate({"refresh_token": "token-456"})
    assert r3.refresh_token == "token-456"


def test_to_login_response_always_includes_access_and_refresh_tokens_for_web():
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        full_name="Web User",
        is_active=True,
        push_notifications_enabled=True,
        is_verified=True,
        mfa_enabled=False,
        can_drive=False,
    )
    tokens = AuthenticatedTokens(
        access_token="mock-jwt-access-token",
        refresh_token="mock-opaque-refresh-token",
        expires_in=3600,
        user=user,
    )

    # When is_web is True, both access_token and refresh_token MUST be returned in the body
    resp = _to_login_response(tokens, include_refresh_in_body=True, is_web=True)
    assert resp.access_token == "mock-jwt-access-token"
    assert resp.refresh_token == "mock-opaque-refresh-token"
    assert resp.expires_in == 3600


@pytest.mark.asyncio
async def test_auth_service_refresh_concurrent_grace_period():
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token_id = uuid.uuid4()
    raw_token = "valid-refresh-token-xyz"
    token_hash = hash_opaque_token(raw_token)

    now = datetime.now(UTC)

    # Token was rotated 5 seconds ago by a concurrent request
    rotated_token = RefreshToken(
        id=token_id,
        session_id=session_id,
        token_hash=token_hash,
        expires_at=now + timedelta(days=30),
        revoked_at=now - timedelta(seconds=5),
        revoked_reason="rotated",
    )

    session = UserSession(
        id=session_id,
        user_id=user_id,
        is_active=True,
        expires_at=now + timedelta(days=30),
    )

    user = User(
        id=user_id,
        email="concurrent@example.com",
        full_name="Concurrent User",
        is_active=True,
    )
    user.roles = []

    mock_refresh_repo = AsyncMock()
    mock_refresh_repo.get_by_hash.return_value = rotated_token
    mock_session_repo = AsyncMock()
    mock_session_repo.get_by_id.return_value = session
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = user

    service = AuthService(
        user_repo=mock_user_repo,
        session_repo=mock_session_repo,
        refresh_token_repo=mock_refresh_repo,
        mfa_repo=AsyncMock(),
        password_reset_repo=AsyncMock(),
        email_verification_repo=AsyncMock(),
        oauth_account_repo=AsyncMock(),
        audit_service=AsyncMock(),
    )

    ctx = RequestContext(ip_address="127.0.0.1", user_agent="test-browser")

    # Second concurrent refresh call should succeed within grace period
    result = await service.refresh(raw_refresh_token=raw_token, ctx=ctx)

    assert result.access_token is not None
    assert result.refresh_token == raw_token
    # Session must NOT be revoked
    mock_session_repo.revoke.assert_not_called()
