"""Regression guard for issue 9: OAuth provider tokens must never be persisted.

The OAuth login/link flows receive a provider `id_token`/access token, verify it
against the provider (Google tokeninfo / Apple JWKS), then discard it.
`OAuthAccount` stores only the identity metadata needed for account linking and
deduplication — never the token itself. These tests lock that invariant in so a
future change cannot silently add token persistence.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from pawguard.core.constants import DeviceType
from pawguard.core.security import generate_opaque_token
from pawguard.modules.auth.models import OAuthAccount, User, UserSession
from pawguard.modules.auth.schemas import DeviceContext
from pawguard.modules.auth.service import AuthService, RequestContext

_UNSAFE_COLUMN_NAMES = ("provider_token", "access_token", "refresh_token", "token", "secret")

_OAUTH_ACCOUNT_COLUMNS = {
    "id",
    "created_at",
    "updated_at",
    "user_id",
    "provider",
    "provider_user_id",
    "provider_email",
    "display_name",
    "picture_url",
    "created_by",
    "updated_by",
}


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


def _stored_values(record: object) -> str:
    """Join the values of `__dict__` (ORM) or `__slots__` (AuthenticatedTokens)."""
    if hasattr(record, "__dict__"):
        return "\n".join(str(v) for v in record.__dict__.values())
    return "\n".join(str(getattr(record, slot)) for slot in getattr(type(record), "__slots__", []))


class TestOAuthAccountSchema:
    def test_model_has_no_token_columns(self) -> None:
        columns = {c.name for c in OAuthAccount.__table__.columns}
        for unsafe in _UNSAFE_COLUMN_NAMES:
            assert unsafe not in columns

    def test_model_stores_only_identity_metadata(self) -> None:
        columns = {c.name for c in OAuthAccount.__table__.columns}
        assert columns == _OAUTH_ACCOUNT_COLUMNS


class TestOAuthTokenNotPersisted:
    @pytest.fixture
    def claims(self) -> dict[str, str]:
        return {
            "sub": "google-user-123",
            "email": "alice@example.com",
            "name": "Alice Example",
            "picture": "https://example.com/alice.png",
        }

    async def test_link_oauth_account_does_not_store_token(self, claims) -> None:
        oauth_repo = AsyncMock()
        oauth_repo.get_by_provider.return_value = None
        svc = _make_service(oauth_account_repo=oauth_repo)
        svc._verify_oauth_token = AsyncMock(return_value=claims)

        provider_token = f"ya29.a0-raw-token-{generate_opaque_token()}"
        account = await svc.link_oauth_account(
            user_id=uuid.uuid4(),
            provider="google",
            provider_token=provider_token,
            ctx=RequestContext(ip_address="127.0.0.1", user_agent="pytest"),
        )

        created: OAuthAccount = oauth_repo.create.call_args.args[0]
        assert created.provider_user_id == "google-user-123"
        assert provider_token not in _stored_values(created)
        assert provider_token not in _stored_values(account)

    async def test_oauth_login_does_not_store_token(self, claims) -> None:
        oauth_repo = AsyncMock()
        oauth_repo.get_by_provider.return_value = None
        user_repo = AsyncMock()
        user_repo.get_by_email.return_value = None
        session_repo = AsyncMock()

        user = User(
            email="alice@example.com",
            full_name="Alice Example",
            hashed_password="unused",
            is_active=True,
            is_verified=True,
        )
        session = UserSession(
            user_id=user.id,
            device_id="dev-001",
            device_name="Test device",
            device_type=DeviceType.UNKNOWN,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        session_repo.create.return_value = session
        user_repo.get_by_id.return_value = user

        svc = _make_service(
            oauth_account_repo=oauth_repo, user_repo=user_repo, session_repo=session_repo
        )
        svc._verify_oauth_token = AsyncMock(return_value=claims)

        provider_token = f"ya29.a0-raw-token-{generate_opaque_token()}"
        tokens = await svc.oauth_login(
            provider="google",
            provider_token=provider_token,
            device=DeviceContext(device_id="dev-001", device_name="Test device"),
            ctx=RequestContext(ip_address="127.0.0.1", user_agent="pytest"),
        )

        created_account: OAuthAccount = oauth_repo.create.call_args.args[0]
        created_user: User = user_repo.create.call_args.args[0]
        for record in (created_account, created_user, tokens):
            assert provider_token not in _stored_values(record)
        assert created_account.provider_user_id == "google-user-123"
