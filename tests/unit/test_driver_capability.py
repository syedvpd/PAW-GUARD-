"""Unit tests for driver capability (can_drive) across auth, rescue, fleet, and schemas."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ValidationFailedError
from pawguard.modules.auth.models import User
from pawguard.modules.auth.service import AdminService
from pawguard.modules.fleet.schemas import VehicleCreate, VehicleUpdate
from pawguard.modules.fleet.service import FleetService
from pawguard.modules.notifications.schemas import NotificationResponse
from pawguard.modules.rescue.models import RescueStatus
from pawguard.modules.rescue.schemas import (
    AgentAvailabilityResponse,
    NearbyAgentResponse,
    RescueDispatchUpdate,
)
from pawguard.modules.rescue.service import RescueService


@pytest.mark.asyncio
class TestDriverCapabilityAuth:
    async def test_user_can_drive_default_false(self):
        user = User(
            email="agent1@pawguard.com",
            full_name="Agent One",
            hashed_password="hash",
            can_drive=False,
        )
        assert user.can_drive is False

    async def test_admin_update_user_can_drive(self):
        user = User(
            id=uuid.uuid4(),
            email="agent2@pawguard.com",
            full_name="Agent Two",
            hashed_password="hash",
            can_drive=False,
        )
        mock_user_repo = AsyncMock()
        mock_user_repo.get_by_id.return_value = user
        mock_user_repo._session = AsyncMock()
        mock_role_repo = AsyncMock()
        mock_perm_repo = AsyncMock()
        mock_user_role_repo = AsyncMock()
        mock_audit = AsyncMock()

        service = AdminService(
            user_repo=mock_user_repo,
            role_repo=mock_role_repo,
            permission_repo=mock_perm_repo,
            user_role_repo=mock_user_role_repo,
            audit_service=mock_audit,
        )

        updated = await service.update_user(user.id, can_drive=True)
        assert updated.can_drive is True


@pytest.mark.asyncio
class TestDriverCapabilityRescue:
    async def test_nearby_agent_response_schema(self):
        agent_id = uuid.uuid4()
        res = NearbyAgentResponse(
            agent_id=agent_id,
            name="Driver Dave",
            can_drive=True,
        )
        assert res.can_drive is True

        res_nodrive = NearbyAgentResponse(
            agent_id=agent_id,
            name="Walker Wendy",
        )
        assert res_nodrive.can_drive is False

    async def test_agent_availability_response_schema(self):
        agent_id = uuid.uuid4()
        res = AgentAvailabilityResponse(
            agent_id=agent_id,
            name="Driver Dave",
            status="available",
            can_drive=True,
        )
        assert res.can_drive is True

    async def test_dispatch_accepts_agent_without_can_drive(self):
        mock_repo = AsyncMock()
        mock_audit = AsyncMock()
        service = RescueService(repository=mock_repo, audit_service=mock_audit)

        driver_id = uuid.uuid4()
        request_id = uuid.uuid4()
        non_driver = User(
            id=driver_id,
            full_name="Foot Agent",
            email="foot@pawguard.com",
            hashed_password="hash",
            can_drive=False,
        )
        mock_repo.get_request_by_id.return_value = MagicMock(status=RescueStatus.VERIFIED)
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.get_active_dispatch_by_vehicle_id.return_value = None
        mock_repo._session = AsyncMock()
        mock_repo._session.get.return_value = non_driver
        mock_repo.create_dispatch.return_value = MagicMock()
        mock_repo.create_dispatch_agent.return_value = MagicMock()

        res = await service.dispatch_team(
            request_id=request_id,
            assigned_driver_id=driver_id,
        )
        assert res is not None

    async def test_dispatch_accepts_driver_with_can_drive(self):
        mock_repo = AsyncMock()
        mock_audit = AsyncMock()
        service = RescueService(repository=mock_repo, audit_service=mock_audit)

        driver_id = uuid.uuid4()
        request_id = uuid.uuid4()
        authorized_driver = User(
            id=driver_id,
            full_name="Authorized Driver",
            email="driver@pawguard.com",
            hashed_password="hash",
            can_drive=True,
        )
        mock_repo.get_request_by_id.return_value = MagicMock(status=RescueStatus.VERIFIED)
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.get_active_dispatch_by_vehicle_id.return_value = None
        mock_repo._session = AsyncMock()
        mock_repo._session.get.return_value = authorized_driver
        mock_repo.create_dispatch.return_value = MagicMock()
        mock_repo.create_dispatch_agent.return_value = MagicMock()

        res = await service.dispatch_team(
            request_id=request_id,
            assigned_driver_id=driver_id,
        )
        assert res is not None

    async def test_reassign_accepts_driver_without_can_drive(self):
        mock_repo = AsyncMock()
        mock_audit = AsyncMock()
        service = RescueService(repository=mock_repo, audit_service=mock_audit)

        dispatch_id = uuid.uuid4()
        new_driver_id = uuid.uuid4()
        mock_dispatch = MagicMock(id=dispatch_id, rescue_request_id=uuid.uuid4())
        mock_repo.get_dispatch_by_id.return_value = mock_dispatch
        mock_repo._session = AsyncMock()
        non_driver = User(
            id=new_driver_id,
            full_name="Walker",
            email="walker@pawguard.com",
            hashed_password="hash",
            can_drive=False,
        )
        mock_repo._session.get.return_value = non_driver

        updated = await service.update_dispatch(
            dispatch_id=dispatch_id,
            payload=RescueDispatchUpdate(assigned_driver_id=new_driver_id),
        )
        assert updated.assigned_driver_id == new_driver_id


@pytest.mark.asyncio
class TestDriverCapabilityFleet:
    async def test_create_vehicle_rejects_non_driver(self):
        mock_repo = AsyncMock()
        mock_repo.get_vehicle_by_plate.return_value = None
        mock_repo._session = AsyncMock()
        non_driver = User(
            id=uuid.uuid4(),
            full_name="Foot Staff",
            email="foot@pawguard.com",
            hashed_password="hash",
            can_drive=False,
        )
        mock_repo._session.get.return_value = non_driver

        service = FleetService(repository=mock_repo)
        payload = VehicleCreate(
            make_model="Toyota HiAce",
            license_plate="TS09AB1234",
            primary_driver_id=non_driver.id,
        )
        with pytest.raises(ValidationFailedError, match="not authorized to drive"):
            await service.create_vehicle(payload)

    async def test_update_vehicle_rejects_non_driver(self):
        mock_repo = AsyncMock()
        vehicle_id = uuid.uuid4()
        mock_repo.get_vehicle.return_value = MagicMock(id=vehicle_id, license_plate="TS09AB1234")
        mock_repo._session = AsyncMock()
        non_driver = User(
            id=uuid.uuid4(),
            full_name="Foot Staff",
            email="foot@pawguard.com",
            hashed_password="hash",
            can_drive=False,
        )
        mock_repo._session.get.return_value = non_driver

        service = FleetService(repository=mock_repo)
        payload = VehicleUpdate(
            primary_driver_id=non_driver.id,
        )
        with pytest.raises(ValidationFailedError, match="not authorized to drive"):
            await service.update_vehicle(vehicle_id, payload)


class TestBugFixesMediaAndNotifications:
    def test_notification_response_module_inference(self):
        notif = NotificationResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="Rescue alert",
            body="New rescue dispatched",
            notification_type="dispatch",
            action_url="/rescue/dispatches/123",
            is_broadcast=False,
            is_read=False,
            created_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
        )
        assert notif.module == "rescue"

        foster_notif = NotificationResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="Foster checkup",
            body="Checkup due",
            notification_type="foster_reminder",
            action_url="/fosters/placements/456",
            is_broadcast=False,
            is_read=False,
            created_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
        )
        assert foster_notif.module == "foster"
