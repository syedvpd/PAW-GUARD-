"""Unit tests for Rescue Notification Governance Engine triggers and reporter_user_id mapping."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from pawguard.modules.rescue.models import (
    RescueDispatch,
    RescuePhysicalCondition,
    RescueRequest,
    RescueStatus,
)
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.service import RescueService


class TestRescueNotificationsAndReporterMapping:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=RescueRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return RescueService(
            repository=mock_repo,
            audit_service=None,
            dog_repo=None,
            redis_client=None,
            arq_pool=None,
        )

    @pytest.mark.asyncio
    async def test_report_incident_binds_actor_id_as_reporter_user_id(self, service, mock_repo):
        actor_id = uuid.uuid4()
        mock_repo.get_request_by_ticket.return_value = None

        created_request = None

        async def fake_create_request(req):
            nonlocal created_request
            created_request = req

        mock_repo.create_request.side_effect = fake_create_request
        mock_repo.get_request_by_id.side_effect = lambda req_id: created_request

        with (
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_user_ids_by_roles",
                new_callable=AsyncMock,
                return_value=[uuid.uuid4()],
            ),
            patch(
                "pawguard.modules.rescue.service._send_governed_notification",
                new_callable=AsyncMock,
            ) as mock_send_notif,
        ):
            res = await service.report_incident(
                reporter_name="Jane Doe",
                reporter_phone="+1234567890",
                reporter_email="jane@example.com",
                is_anonymous=False,
                location_address="123 Rescue St",
                physical_condition=RescuePhysicalCondition.INJURED,
                actor_id=actor_id,
            )

            assert res.reporter_user_id == actor_id
            mock_send_notif.assert_called()
            call_kwargs = mock_send_notif.call_args.kwargs
            assert call_kwargs["trigger_code"] == "rescue_incident_reported"
            assert actor_id in call_kwargs["target_user_ids"]

    @pytest.mark.asyncio
    async def test_dispatch_team_notifies_reporter(self, service, mock_repo):
        request_id = uuid.uuid4()
        reporter_user_id = uuid.uuid4()
        driver_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        rescue = RescueRequest(
            id=request_id,
            ticket_number="RES-20260825-0001",
            reporter_name="John",
            reporter_phone="+1234567",
            location_address="Park",
            reporter_user_id=reporter_user_id,
            status=RescueStatus.VERIFIED,
        )

        dispatch = RescueDispatch(
            id=uuid.uuid4(),
            rescue_request_id=request_id,
            assigned_driver_id=driver_id,
        )

        mock_repo.get_request_by_id.return_value = rescue
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = dispatch

        with patch(
            "pawguard.modules.rescue.service._send_governed_notification",
            new_callable=AsyncMock,
        ) as mock_send_notif:
            await service.dispatch_team(
                request_id=request_id,
                assigned_driver_id=driver_id,
                assigned_agent_ids=[agent_id],
                actor_id=uuid.uuid4(),
            )

            mock_send_notif.assert_called_once()
            call_kwargs = mock_send_notif.call_args.kwargs
            assert call_kwargs["trigger_code"] == "rescue_dispatched"
            assert reporter_user_id in call_kwargs["target_user_ids"]
            assert driver_id in call_kwargs["target_user_ids"]
            assert agent_id in call_kwargs["target_user_ids"]
