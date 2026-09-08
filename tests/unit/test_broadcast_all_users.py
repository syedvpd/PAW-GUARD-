"""Untargeted broadcast fans out to every active user."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import BroadcastCreate
from pawguard.modules.notifications.service import NotificationService


@pytest.mark.asyncio
async def test_broadcast_without_targets_hits_all_active_users() -> None:
    active_ids = [uuid.uuid4(), uuid.uuid4()]
    mock_repo = AsyncMock(spec=NotificationRepository)
    mock_repo._session = AsyncMock()
    mock_repo.create_many.side_effect = lambda notifications: notifications
    service = NotificationService(repository=mock_repo)

    with patch("pawguard.modules.auth.repository.UserRepository") as user_repo_cls:
        user_repo_cls.return_value.get_all_active_user_ids = AsyncMock(return_value=active_ids)
        created = await service.broadcast(BroadcastCreate(title="T", body="B"), [])

    assert {n.user_id for n in created} == set(active_ids)
