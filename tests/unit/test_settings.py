"""Unit tests for Settings service and repository."""

from unittest.mock import AsyncMock

import pytest

from pawguard.modules.settings.models import SystemSetting
from pawguard.modules.settings.repository import SystemSettingRepository
from pawguard.modules.settings.schemas import SystemSettingCreate, SystemSettingUpdate
from pawguard.modules.settings.service import AppConfigService, SystemSettingService


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


class TestAppConfigService:
    def test_general_settings(self):
        svc = AppConfigService()
        result = svc.get_general_settings()
        assert result.app_name == "PawGuard"
        assert result.environment == "local"

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
