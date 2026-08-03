"""Unit tests for OAuth provider-token audience validation (auth H-1).

Google/Apple ID tokens must be issued for OUR client (`aud` matches the
configured client id) or they are rejected. OAuth login FAILS CLOSED when the
client id is not configured, so a misconfiguration can never silently accept
another app's ID token (cross-app token confusion / account takeover).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.config import get_settings
from pawguard.modules.auth.exceptions import InvalidCredentialsError
from pawguard.modules.auth.service import AuthService


@pytest.mark.asyncio
class TestOAuthAudienceValidation:
    @staticmethod
    def _patch_provider_http(monkeypatch, payload: dict, status: int = 200) -> None:
        """Replace httpx.AsyncClient with a fake returning `payload`."""
        import httpx

        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = payload
        client = AsyncMock()
        client.get.return_value = resp
        cm = MagicMock()
        cm.__aenter__.return_value = client
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: cm)

    async def test_google_fails_closed_when_client_id_unset(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "google_oauth_client_id", "")
        with pytest.raises(InvalidCredentialsError, match="not configured"):
            await AuthService._verify_oauth_token_unsafe("google", "any-token")

    async def test_google_accepts_token_issued_for_our_client(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "google_oauth_client_id", "our-client.apps.googleusercontent.com")
        self._patch_provider_http(
            monkeypatch,
            {
                "sub": "google-user-1",
                "email": "alice@example.com",
                "email_verified": True,
                "name": "Alice",
                "aud": "our-client.apps.googleusercontent.com",
            },
        )
        data = await AuthService._verify_oauth_token_unsafe("google", "token")
        assert data["sub"] == "google-user-1"
        assert data["email"] == "alice@example.com"

    async def test_google_rejects_token_for_another_app(self, monkeypatch) -> None:
        monkeypatch.setattr(
            get_settings(), "google_oauth_client_id", "our-client.apps.googleusercontent.com"
        )
        self._patch_provider_http(
            monkeypatch,
            {
                "sub": "google-user-1",
                "email": "alice@example.com",
                "email_verified": True,
                "aud": "some-other-app.apps.googleusercontent.com",
            },
        )
        with pytest.raises(InvalidCredentialsError, match="not issued for this application"):
            await AuthService._verify_oauth_token_unsafe("google", "token")

    async def test_apple_fails_closed_when_client_id_unset(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "apple_oauth_client_id", "")
        with pytest.raises(InvalidCredentialsError, match="not configured"):
            await AuthService._verify_oauth_token_unsafe("apple", "any-token")

    async def test_unsupported_provider_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "google_oauth_client_id", "x")
        with pytest.raises(InvalidCredentialsError, match="Unsupported OAuth provider"):
            await AuthService._verify_oauth_token_unsafe("github", "token")
