"""Regression tests for FCM credential configuration aliases (BUG-14)."""

import json

import pytest

from pawguard.core.config import Settings


class TestFCMCredentialAliases:
    """Verify that FCM credentials can be loaded from multiple env-var names."""

    def _make_settings(self, monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
        for key, val in env.items():
            monkeypatch.setenv(key, val)
        # Clear lru_cache so a fresh Settings() picks up the new env vars.
        Settings.__init__.__wrapped__  # type: ignore[attr-defined]  # noqa: B018
        return Settings()

    def test_canonical_fcm_credentials_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FCM_CREDENTIALS_PATH", "/etc/firebase/sa.json")
        settings = Settings()
        assert settings.fcm_credentials_path == "/etc/firebase/sa.json"

    def test_google_application_credentials_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/etc/firebase/sa.json")
        settings = Settings()
        assert settings.fcm_credentials_path == "/etc/firebase/sa.json"

    def test_firebase_credentials_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREBASE_CREDENTIALS", "/etc/firebase/sa.json")
        settings = Settings()
        assert settings.fcm_credentials_path == "/etc/firebase/sa.json"

    def test_canonical_fcm_credentials_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = json.dumps({"type": "service_account", "project_id": "test"})
        monkeypatch.setenv("FCM_CREDENTIALS_JSON", payload)
        settings = Settings()
        assert settings.fcm_credentials_json == payload

    def test_firebase_credentials_json_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = json.dumps({"type": "service_account", "project_id": "test"})
        monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", payload)
        settings = Settings()
        assert settings.fcm_credentials_json == payload

    def test_inline_json_in_path_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FIREBASE_CREDENTIALS may contain raw JSON; the path field should accept it."""
        payload = json.dumps({"type": "service_account", "project_id": "test"})
        monkeypatch.setenv("FIREBASE_CREDENTIALS", payload)
        settings = Settings()
        assert settings.fcm_credentials_path == payload
        # push_service should detect it as inline JSON (starts with '{').

    def test_defaults_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FCM_CREDENTIALS_PATH", "")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        monkeypatch.setenv("FIREBASE_CREDENTIALS", "")
        monkeypatch.setenv("FCM_CREDENTIALS_JSON", "")
        monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", "")
        settings = Settings()
        assert settings.fcm_credentials_path == ""
        assert settings.fcm_credentials_json == ""
