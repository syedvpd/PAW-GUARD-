"""Unit tests for NotificationService and NotificationRepository."""

import uuid
from unittest.mock import AsyncMock

import pytest

from pawguard.modules.notifications.models import Notification
from pawguard.modules.notifications.repository import (
    NotificationPreferenceRepository,
    NotificationRepository,
)
from pawguard.modules.notifications.schemas import BroadcastCreate, NotificationCreate
from pawguard.modules.notifications.service import (
    NotificationPreferenceService,
    NotificationService,
)


class TestNotificationService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=NotificationRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return NotificationService(mock_repo)

    async def test_create_notification(self, service, mock_repo):
        mock_repo.create.return_value = Notification(
            user_id=uuid.uuid4(), title="Test", body="Body"
        )
        payload = NotificationCreate(user_id=uuid.uuid4(), title="Test", body="Body")
        result = await service.create_notification(
            payload, actor_id=uuid.uuid4(), ip_address="127.0.0.1"
        )
        assert result.title == "Test"

    async def test_broadcast(self, service, mock_repo):
        mock_repo.create_many.return_value = [
            Notification(user_id=uuid.uuid4(), title="Broadcast", body="Body"),
            Notification(user_id=uuid.uuid4(), title="Broadcast", body="Body"),
        ]
        payload = BroadcastCreate(title="Broadcast", body="Body")
        user_ids = [uuid.uuid4(), uuid.uuid4()]
        results = await service.broadcast(
            payload, user_ids, actor_id=uuid.uuid4(), ip_address="127.0.0.1"
        )
        assert len(results) == 2
        mock_repo.create_many.assert_awaited_once()

    async def test_count_unread(self, service, mock_repo):
        mock_repo.count_unread.return_value = 5
        count = await service.count_unread(uuid.uuid4())
        assert count == 5

    async def test_mark_read_not_found(self, service, mock_repo):
        mock_repo.mark_read.return_value = None
        from pawguard.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await service.mark_read(uuid.uuid4(), uuid.uuid4())


class TestNotificationPreferenceService:
    @pytest.fixture
    def mock_repo(self):
        return AsyncMock(spec=NotificationPreferenceRepository)

    @pytest.fixture
    def service(self, mock_repo):
        return NotificationPreferenceService(mock_repo)

    async def test_get_preferences_creates_default(self, service, mock_repo):
        mock_repo.get_by_user.return_value = None
        from pawguard.modules.notifications.models import NotificationPreference

        mock_repo.upsert.return_value = NotificationPreference(user_id=uuid.uuid4())
        result = await service.get_preferences(uuid.uuid4())
        assert result is not None
