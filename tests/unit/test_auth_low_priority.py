"""Unit tests for the Module 1 (Auth) Low-priority fixes.

L-1: every AuthService audit record carries client context — register(),
     account lockout (via _register_failed_attempt) and update_profile()
     previously wrote rows with no ip_address/user_agent.
L-2: resolve_client_ip() trusts the leftmost X-Forwarded-For hop so audit
     rows and rate-limit buckets key on the real caller, not the proxy.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pawguard.core.rate_limiter import resolve_client_ip
from pawguard.modules.auth.models import AuthAuditEventType, User
from pawguard.modules.auth.service import AuthService, RequestContext


class _FakeRequest:
    """Minimal Request stand-in for resolve_client_ip()."""

    def __init__(self, *, headers: dict[str, str], client_host: str | None) -> None:
        self.headers = headers
        self.client = SimpleNamespace(host=client_host) if client_host else None


def _ctx() -> RequestContext:
    return RequestContext(ip_address="203.0.113.9", user_agent="test-agent/1.0")


def _make_auth_service(**overrides: object) -> AuthService:
    kwargs: dict[str, object] = dict(
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
class TestAuditContextOnRegistration:
    async def test_register_records_client_context(self) -> None:
        audit = AsyncMock()
        user_repo = AsyncMock()
        user = User(
            id=uuid.uuid4(),
            email="jane@example.com",
            full_name="Jane Doe",
            hashed_password="x",
            is_active=True,
        )
        user_repo.get_by_email.return_value = None
        user_repo.get_default_role.return_value = None
        user_repo.create.return_value = user
        user_repo.get_by_id.return_value = user
        svc = _make_auth_service(user_repo=user_repo, audit_service=audit)

        await svc.register(
            email="jane@example.com",
            password="StrongP@ss99",
            full_name="Jane Doe",
            phone="+1-555-0100",
            ctx=_ctx(),
        )

        audit.record.assert_awaited_once()
        kwargs = audit.record.call_args.kwargs
        assert kwargs["event_type"] == AuthAuditEventType.REGISTERED
        assert kwargs["ip_address"] == "203.0.113.9"
        assert kwargs["user_agent"] == "test-agent/1.0"


@pytest.mark.asyncio
class TestAuditContextOnLockout:
    async def test_account_lockout_records_client_context(self) -> None:
        audit = AsyncMock()
        user = User(
            id=uuid.uuid4(),
            email="jane@example.com",
            full_name="Jane Doe",
            hashed_password="x",
            is_active=True,
            failed_login_count=4,
        )
        svc = _make_auth_service(audit_service=audit)

        await svc._register_failed_attempt(user, _ctx())

        assert user.failed_login_count == 5
        assert user.locked_until is not None
        kwargs = audit.record.call_args.kwargs
        assert kwargs["event_type"] == AuthAuditEventType.ACCOUNT_LOCKED
        assert kwargs["ip_address"] == "203.0.113.9"
        assert kwargs["user_agent"] == "test-agent/1.0"


@pytest.mark.asyncio
class TestAuditContextOnProfileUpdate:
    async def test_update_profile_records_client_context(self) -> None:
        audit = AsyncMock()
        user_repo = AsyncMock()
        user = User(
            id=uuid.uuid4(),
            email="jane@example.com",
            full_name="Jane Doe",
            hashed_password="x",
            is_active=True,
        )
        user_repo.get_by_id.return_value = user
        svc = _make_auth_service(user_repo=user_repo, audit_service=audit)

        await svc.update_profile(user.id, full_name="Jane D.", ctx=_ctx())

        kwargs = audit.record.call_args.kwargs
        assert kwargs["event_type"] == AuthAuditEventType.PROFILE_UPDATED
        assert kwargs["ip_address"] == "203.0.113.9"
        assert kwargs["user_agent"] == "test-agent/1.0"


@pytest.mark.asyncio
class TestResolveClientIp:
    async def test_prefers_last_xff_hop(self) -> None:
        req = _FakeRequest(
            headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1, 10.0.0.2"},
            client_host="10.0.0.2",
        )
        assert resolve_client_ip(req) == "10.0.0.2"

    async def test_falls_back_to_client_host_without_xff(self) -> None:
        req = _FakeRequest(headers={}, client_host="10.0.0.1")
        assert resolve_client_ip(req) == "10.0.0.1"

    async def test_unknown_when_neither_available(self) -> None:
        req = _FakeRequest(headers={}, client_host=None)
        assert resolve_client_ip(req) == "unknown"

    async def test_strips_whitespace_from_xff_entry(self) -> None:
        req = _FakeRequest(
            headers={"X-Forwarded-For": " 203.0.113.9 , 10.0.0.1"},
            client_host="10.0.0.1",
        )
        assert resolve_client_ip(req) == "10.0.0.1"
