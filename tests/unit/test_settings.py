"""Unit tests for Settings service and repository."""

from unittest.mock import AsyncMock

import pytest

from pawguard.modules.settings.models import SystemSetting
from pawguard.modules.settings.repository import SystemSettingRepository
from pawguard.modules.settings.schemas import (
    PublicContentUpdate,
    SystemSettingCreate,
    SystemSettingUpdate,
)
from pawguard.modules.settings.service import (
    ABOUT_US_KEY,
    DEFAULT_ABOUT_US,
    DEFAULT_MISSION,
    MISSION_KEY,
    AppConfigService,
    PublicContentService,
    SystemSettingService,
)


class TestSystemSettingService:
    @pytest.fixture
    def mock_repo(self):
        return AsyncMock(spec=SystemSettingRepository)

    @pytest.fixture
    def service(self, mock_repo):
        return SystemSettingService(mock_repo)

    async def test_get_setting_found(self, service, mock_repo):
        mock_repo.get_by_key.return_value = SystemSetting(
            key="app.name", value="PawGuard", category="general"
        )
        result = await service.get_setting("app.name")
        assert result.key == "app.name"
        assert result.value == "PawGuard"

    async def test_get_setting_not_found(self, service, mock_repo):
        mock_repo.get_by_key.return_value = None
        from pawguard.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await service.get_setting("nonexistent")

    async def test_create_setting(self, service, mock_repo):
        mock_repo.get_by_key.return_value = None
        mock_repo.create.return_value = SystemSetting(key="new.key", value="val", category="test")
        payload = SystemSettingCreate(key="new.key", value="val", category="test")
        result = await service.create_setting(payload)
        assert result.key == "new.key"

    async def test_create_setting_duplicate(self, service, mock_repo):
        mock_repo.get_by_key.return_value = SystemSetting(key="dup", value="val", category="test")
        from pawguard.core.exceptions import ConflictError

        with pytest.raises(ConflictError):
            await service.create_setting(SystemSettingCreate(key="dup", value="val"))

    async def test_update_setting(self, service, mock_repo):
        existing = SystemSetting(key="test.key", value="old", category="test")
        mock_repo.get_by_key.return_value = existing
        result = await service.update_setting("test.key", SystemSettingUpdate(value="new"))
        assert result.value == "new"

    async def test_update_setting_not_found(self, service, mock_repo):
        mock_repo.get_by_key.return_value = None
        from pawguard.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await service.update_setting("nope", SystemSettingUpdate(value="x"))

    async def test_list_all(self, service, mock_repo):
        mock_repo.list_all.return_value = [
            SystemSetting(key="a", value="1", category="g"),
            SystemSetting(key="b", value="2", category="g"),
        ]
        results = await service.list_all()
        assert len(results) == 2


class TestPublicContentService:
    @pytest.fixture
    def mock_repo(self):
        return AsyncMock(spec=SystemSettingRepository)

    @pytest.fixture
    def service(self, mock_repo):
        return PublicContentService(mock_repo)

    def _setting(self, key, value):
        return SystemSetting(key=key, value=value, category="content")

    async def test_get_content_uses_defaults_when_missing(self, service, mock_repo):
        mock_repo.get_by_key.return_value = None
        result = await service.get_content()
        assert result.about_us == DEFAULT_ABOUT_US
        assert result.mission == DEFAULT_MISSION
        assert result.updated_at is None

    async def test_get_content_returns_stored_values(self, service, mock_repo):
        def _side_effect(key, *args, **kwargs):
            if key == ABOUT_US_KEY:
                return self._setting(ABOUT_US_KEY, "Custom about")
            return self._setting(MISSION_KEY, "Custom mission")

        mock_repo.get_by_key.side_effect = _side_effect
        result = await service.get_content()
        assert result.about_us == "Custom about"
        assert result.mission == "Custom mission"

    async def test_update_content_creates_missing_settings(self, service, mock_repo):
        stored: dict[str, str] = {}

        async def _get_by_key(key, *args, **kwargs):
            return self._setting(key, stored[key]) if key in stored else None

        async def _create(setting):
            stored[setting.key] = setting.value
            return setting

        mock_repo.get_by_key.side_effect = _get_by_key
        mock_repo.create.side_effect = _create

        result = await service.update_content(
            PublicContentUpdate(about_us="New about", mission="New mission")
        )
        assert stored == {ABOUT_US_KEY: "New about", MISSION_KEY: "New mission"}
        assert result.about_us == "New about"
        assert result.mission == "New mission"

    async def test_update_content_updates_existing_settings(self, service, mock_repo):
        stored = {
            ABOUT_US_KEY: self._setting(ABOUT_US_KEY, "old about"),
            MISSION_KEY: self._setting(MISSION_KEY, "old mission"),
        }
        mock_repo.get_by_key.side_effect = lambda key, *a, **k: stored.get(key)

        result = await service.update_content(
            PublicContentUpdate(about_us="Edited", mission="Edited mission")
        )
        assert mock_repo.create.await_count == 0
        assert result.about_us == "Edited"
        assert result.mission == "Edited mission"
        assert stored[ABOUT_US_KEY].value == "Edited"
        assert stored[MISSION_KEY].value == "Edited mission"

    async def test_update_content_rejects_empty_payload(self, service, mock_repo):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PublicContentUpdate()


class TestAppConfigService:
    def test_general_settings(self):
        svc = AppConfigService()
        result = svc.get_general_settings()
        assert result.app_name == "PawGuard"
        assert result.environment == "test"

    def test_email_settings(self):
        svc = AppConfigService()
        result = svc.get_email_settings()
        assert "mail_from" in result
        assert "mail_host" in result

    def test_storage_settings(self):
        svc = AppConfigService()
        result = svc.get_storage_settings()
        assert "s3_bucket_name" in result
        assert "s3_region" in result
