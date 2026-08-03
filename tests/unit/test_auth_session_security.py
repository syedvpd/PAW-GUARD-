"""Unit tests for auth session-security fixes (H-2 / H-3).

- `AuthService.refresh` must reject a session whose `expires_at` has passed
  (otherwise sessions never expire via the refresh path).
- The auth `RateLimiter` must resolve the caller's real IP from
  `X-Forwarded-For` so per-IP brute-force protection survives a reverse proxy.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.rate_limiter import rate_limit
from pawguard.modules.auth.exceptions import InvalidSessionError
from pawguard.modules.auth.models import RefreshToken, UserSession
from pawguard.modules.auth.service import AuthService, RequestContext


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
    return AuthService(**kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestRefreshSessionExpiry:
    async def test_refresh_rejects_expired_session(self) -> None:
        now = datetime.now(UTC)
        session_id = uuid.uuid4()
        refresh_repo = AsyncMock()
        refresh_repo.get_by_hash.return_value = RefreshToken(
            id=uuid.uuid4(),
            session_id=session_id,
            token_hash="hash",
            expires_at=now + timedelta(minutes=5),
        )
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = UserSession(
            id=session_id,
            user_id=uuid.uuid4(),
            is_active=True,
            expires_at=now - timedelta(minutes=1),
        )
        svc = _make_service(refresh_token_repo=refresh_repo, session_repo=session_repo)

        with pytest.raises(InvalidSessionError, match="expired"):
            await svc.refresh(
                raw_refresh_token="raw-token",
                ctx=RequestContext(ip_address="127.0.0.1", user_agent="pytest"),
            )

    async def test_refresh_accepts_active_unexpired_session(self) -> None:
        now = datetime.now(UTC)
        session_id = uuid.uuid4()
        refresh_repo = AsyncMock()
        refresh_repo.get_by_hash.return_value = RefreshToken(
            id=uuid.uuid4(),
            session_id=session_id,
            token_hash="hash",
            expires_at=now + timedelta(minutes=5),
        )
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = UserSession(
            id=session_id,
            user_id=uuid.uuid4(),
            is_active=True,
            expires_at=now + timedelta(days=10),
        )
        user_repo = AsyncMock()
        user = MagicMock()
        user.id = uuid.uuid4()
        user.is_active = True
        user.roles = []
        user_repo.get_by_id.return_value = user
        svc = _make_service(
            refresh_token_repo=refresh_repo,
            session_repo=session_repo,
            user_repo=user_repo,
        )

        tokens = await svc.refresh(
            raw_refresh_token="raw-token",
            ctx=RequestContext(ip_address="127.0.0.1", user_agent="pytest"),
        )
        assert tokens.access_token


class _FakeState:
    user_id = None


class _FakeRequest:
    """Minimal stand-in for a Starlette Request: headers, client, state."""

    def __init__(self, headers: dict, host: str = "127.0.0.1") -> None:
        self.headers = headers
        self.client = type("Client", (), {"host": host})()
        self.state = _FakeState()


@pytest.mark.asyncio
class TestRateLimiterXForwardedFor:
    async def test_uses_first_forwarded_ip(self) -> None:
        limiter = rate_limit("login", 10, 60)
        request = _FakeRequest({"X-Forwarded-For": "203.0.113.5, 10.0.0.1"})
        redis = AsyncMock()
        redis.incr.return_value = 1

        await limiter(request, redis)

        key = redis.incr.call_args.args[0]
        assert "203.0.113.5" in key
        assert "127.0.0.1" not in key

    async def test_falls_back_to_client_host_without_xff(self) -> None:
        limiter = rate_limit("login", 10, 60)
        request = _FakeRequest({}, host="198.51.100.7")
        redis = AsyncMock()
        redis.incr.return_value = 1

        await limiter(request, redis)

        key = redis.incr.call_args.args[0]
        assert "198.51.100.7" in key

    async def test_enforces_limit(self) -> None:
        limiter = rate_limit("login", 2, 60)
        request = _FakeRequest({"X-Forwarded-For": "203.0.113.9"})
        redis = AsyncMock()
        redis.incr.side_effect = [1, 2, 3]

        await limiter(request, redis)
        await limiter(request, redis)
        from pawguard.core.exceptions import TooManyRequestsError

        with pytest.raises(TooManyRequestsError):
            await limiter(request, redis)
