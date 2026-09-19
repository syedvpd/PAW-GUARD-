"""Tests for the fleet scheduled background jobs (PRR 3.13)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pawguard.modules.notifications.schemas import NotificationCreate
from pawguard.workers.jobs.fleet_jobs import (
    check_equipment_checkout_expiry,
    check_fleet_maintenance_due,
    check_vehicle_insurance_expiry,
)


class TestFleetScheduledJobs:
    """Test fleet alert jobs (mock session + notification service)."""

    @staticmethod
    def _due(days: int):
        vehicle = MagicMock()
        vehicle.id = uuid.uuid4()
        vehicle.license_plate = "RESCUE-01"
        record = MagicMock()
        record.next_due_date = date.today() + timedelta(days=days)
        return vehicle, record

    def _wire(self, mock_repo_cls, mock_session_factory, due, staff):
        mock_repo_cls.return_value.list_maintenance_due = AsyncMock(return_value=due)
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = staff
        mock_session = AsyncMock()
        mock_session.execute.return_value = staff_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.FleetRepository")
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_fleet_maintenance_due(
        self, mock_notif_cls, mock_session_factory, mock_repo_cls
    ):
        """Should alert staff with vehicle:read when maintenance is due within 14 days."""
        staff_user_id = uuid.uuid4()
        self._wire(mock_repo_cls, mock_session_factory, [self._due(7)], [staff_user_id])
        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_fleet_maintenance_due({})

        cutoff = mock_repo_cls.return_value.list_maintenance_due.call_args.args[0]
        assert cutoff == date.today() + timedelta(days=14)
        mock_notif.create_notification.assert_called_once()
        payload = mock_notif.create_notification.call_args.kwargs["payload"]
        assert isinstance(payload, NotificationCreate)
        assert payload.user_id == staff_user_id
        assert payload.notification_type == "fleet_alert"
        assert "maintenance due" in payload.body
        assert "RESCUE-01" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.FleetRepository")
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_fleet_maintenance_due_nothing_due(
        self, mock_notif_cls, mock_session_factory, mock_repo_cls
    ):
        """No maintenance within the window -> no notifications."""
        self._wire(mock_repo_cls, mock_session_factory, [], [uuid.uuid4()])
        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_fleet_maintenance_due({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.FleetRepository")
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_fleet_maintenance_due_overdue(
        self, mock_notif_cls, mock_session_factory, mock_repo_cls
    ):
        """Overdue maintenance (next_due_date in the past) should trigger alerts."""
        self._wire(mock_repo_cls, mock_session_factory, [self._due(-5)], [uuid.uuid4()])
        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_fleet_maintenance_due({})

        mock_notif.create_notification.assert_called_once()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.FleetRepository")
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_fleet_maintenance_due_commits(
        self, mock_notif_cls, mock_session_factory, mock_repo_cls
    ):
        """Job should commit the session after sending notifications."""
        mock_session = self._wire(
            mock_repo_cls, mock_session_factory, [self._due(7)], [uuid.uuid4()]
        )
        mock_notif_cls.return_value = AsyncMock()

        await check_fleet_maintenance_due({})

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_vehicle_insurance_expiry(self, mock_notif_cls, mock_session_factory):
        """Should alert staff when vehicle insurance expires within 30 days."""
        vehicle = MagicMock()
        vehicle.license_plate = "RESCUE-01"
        vehicle.insurance_expiry_date = date.today() + timedelta(days=10)

        staff_user_id = uuid.uuid4()
        vehicle_result = MagicMock()
        vehicle_result.scalars.return_value.all.return_value = [vehicle]
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = [staff_user_id]

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [vehicle_result, staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_vehicle_insurance_expiry({})

        mock_notif.create_notification.assert_called_once()
        payload = mock_notif.create_notification.call_args.kwargs["payload"]
        assert isinstance(payload, NotificationCreate)
        assert payload.user_id == staff_user_id
        assert payload.notification_type == "expiry_alert"
        assert "RESCUE-01" in payload.body
        assert "expires" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_vehicle_insurance_expiry_none_expiring(
        self, mock_notif_cls, mock_session_factory
    ):
        """No expiring insurance -> no notifications."""
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = empty_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_vehicle_insurance_expiry({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_vehicle_insurance_expiry_overdue(
        self, mock_notif_cls, mock_session_factory
    ):
        """Already-expired insurance should trigger alerts."""
        vehicle = MagicMock()
        vehicle.license_plate = "AMB-99"
        vehicle.insurance_expiry_date = date.today() - timedelta(days=10)

        staff_user_id = uuid.uuid4()
        vehicle_result = MagicMock()
        vehicle_result.scalars.return_value.all.return_value = [vehicle]
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = [staff_user_id]

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [vehicle_result, staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_vehicle_insurance_expiry({})

        mock_notif.create_notification.assert_called_once()
        payload = mock_notif.create_notification.call_args.kwargs["payload"]
        assert "AMB-99" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_vehicle_insurance_expiry_skips_future_outside_window(
        self, mock_notif_cls, mock_session_factory
    ):
        """Insurance expiring more than 30 days out should not trigger."""
        vehicle = MagicMock()
        vehicle.license_plate = "VET-01"
        vehicle.insurance_expiry_date = date.today() + timedelta(days=60)

        vehicle_result = MagicMock()
        vehicle_result.scalars.return_value.all.return_value = [vehicle]
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.side_effect = [vehicle_result, staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_vehicle_insurance_expiry({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_vehicle_insurance_expiry_commits(
        self, mock_notif_cls, mock_session_factory
    ):
        """Job should commit the session after sending notifications."""
        vehicle = MagicMock()
        vehicle.license_plate = "RESCUE-01"
        vehicle.insurance_expiry_date = date.today() + timedelta(days=10)

        staff_user_id = uuid.uuid4()
        vehicle_result = MagicMock()
        vehicle_result.scalars.return_value.all.return_value = [vehicle]
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = [staff_user_id]

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [vehicle_result, staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_vehicle_insurance_expiry({})

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_equipment_checkout_expiry(self, mock_notif_cls, mock_session_factory):
        """Should alert staff when outstanding equipment is overdue."""
        checkout = MagicMock()
        checkout.equipment_name = "Net Gun"
        checkout.expected_return_at = datetime.now(UTC) - timedelta(days=1)

        staff_user_id = uuid.uuid4()
        checkout_result = MagicMock()
        checkout_result.scalars.return_value.all.return_value = [checkout]
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = [staff_user_id]

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [checkout_result, staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_equipment_checkout_expiry({})

        mock_notif.create_notification.assert_called_once()
        payload = mock_notif.create_notification.call_args.kwargs["payload"]
        assert isinstance(payload, NotificationCreate)
        assert payload.user_id == staff_user_id
        assert payload.notification_type == "fleet_alert"
        assert "Net Gun" in payload.body
        assert "due back" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_equipment_checkout_expiry_none_overdue(
        self, mock_notif_cls, mock_session_factory
    ):
        """No overdue checkouts -> no notifications."""
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = empty_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_equipment_checkout_expiry({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_equipment_checkout_expiry_due_today(
        self, mock_notif_cls, mock_session_factory
    ):
        """Equipment due today (expected_return_at == now) should be flagged."""
        checkout = MagicMock()
        checkout.equipment_name = "Crate"
        checkout.expected_return_at = datetime.now(UTC)

        staff_user_id = uuid.uuid4()
        checkout_result = MagicMock()
        checkout_result.scalars.return_value.all.return_value = [checkout]
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = [staff_user_id]

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [checkout_result, staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_equipment_checkout_expiry({})

        mock_notif.create_notification.assert_called_once()
        payload = mock_notif.create_notification.call_args.kwargs["payload"]
        assert "Crate" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_equipment_checkout_expiry_future_not_flagged(
        self, mock_notif_cls, mock_session_factory
    ):
        """Equipment not yet due should not trigger."""
        checkout = MagicMock()
        checkout.equipment_name = "Trap"
        checkout.expected_return_at = datetime.now(UTC) + timedelta(days=5)

        checkout_result = MagicMock()
        checkout_result.scalars.return_value.all.return_value = [checkout]
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.side_effect = [checkout_result, staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_equipment_checkout_expiry({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_equipment_checkout_expiry_skips_null_expected_return(
        self, mock_notif_cls, mock_session_factory
    ):
        """Checkouts with no expected_return_at should be skipped by the query."""
        # Query filters expected_return_at.isnot(None), so no results returned
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = empty_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_equipment_checkout_expiry({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_equipment_checkout_expiry_commits(
        self, mock_notif_cls, mock_session_factory
    ):
        """Job should commit the session after sending notifications."""
        checkout = MagicMock()
        checkout.equipment_name = "Net Gun"
        checkout.expected_return_at = datetime.now(UTC) - timedelta(days=1)

        staff_user_id = uuid.uuid4()
        checkout_result = MagicMock()
        checkout_result.scalars.return_value.all.return_value = [checkout]
        staff_result = MagicMock()
        staff_result.scalars.return_value.all.return_value = [staff_user_id]

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [checkout_result, staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_equipment_checkout_expiry({})

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_fleet_alert_jobs_skip_when_no_staff_match(
        self, mock_notif_cls, mock_session_factory
    ):
        """A fleet alert with no eligible staff recipient creates nothing."""
        maint = MagicMock()
        maint.vehicle_id = uuid.uuid4()
        maint.next_due_date = date.today() + timedelta(days=3)

        maint_result = MagicMock()
        maint_result.scalars.return_value.all.return_value = [maint]
        no_staff_result = MagicMock()
        no_staff_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [maint_result, no_staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_fleet_maintenance_due({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.fleet_jobs.FleetRepository")
    @patch("pawguard.workers.jobs.fleet_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.fleet_jobs.NotificationService")
    async def test_check_fleet_maintenance_due_multiple_records(
        self, mock_notif_cls, mock_session_factory, mock_repo_cls
    ):
        """Multiple due vehicles should each notify all staff."""
        staff_ids = [uuid.uuid4(), uuid.uuid4()]
        self._wire(mock_repo_cls, mock_session_factory, [self._due(2), self._due(10)], staff_ids)
        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_fleet_maintenance_due({})

        assert mock_notif.create_notification.call_count == 4
