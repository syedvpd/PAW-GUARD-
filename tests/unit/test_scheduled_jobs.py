"""Tests for scheduled background jobs."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pawguard.workers.jobs.scheduled_jobs import (
    check_inventory_expiry,
    check_inventory_low_stock,
    check_vaccination_renewals,
    post_adoption_followups,
    process_sponsorship_charges,
)


class TestScheduledJobs:
    """Test scheduled job functions."""

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_check_inventory_low_stock(self, mock_notif_cls, mock_session_factory):
        """Should alert when stock <= reorder_threshold."""
        item = MagicMock()
        item.name = "Dog Food"
        item.quantity = 5
        item.reorder_threshold = 10
        item.unit = "kg"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [item]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_inventory_low_stock({})

        mock_notif.create_notification.assert_called_once()
        call_kwargs = mock_notif.create_notification.call_args[1]
        assert "Dog Food" in call_kwargs["message"]
        assert "low on stock" in call_kwargs["message"]

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_check_inventory_low_stock_no_alerts(self, mock_notif_cls, mock_session_factory):
        """Should not alert when stock is sufficient."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_inventory_low_stock({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_check_inventory_expiry(self, mock_notif_cls, mock_session_factory):
        """Should alert for items expiring within 30 days."""
        from datetime import date as date_type

        item = MagicMock()
        item.name = "Vaccine"
        item.expiry_date = date_type.today() + timedelta(days=10)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [item]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_inventory_expiry({})

        mock_notif.create_notification.assert_called_once()
        call_kwargs = mock_notif.create_notification.call_args[1]
        assert "Vaccine" in call_kwargs["message"]
        assert "expires" in call_kwargs["message"]

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_check_vaccination_renewals(self, mock_notif_cls, mock_session_factory):
        """Should remind for vaccinations due within 14 days."""
        vax = MagicMock()
        vax.vaccine_name = "Rabies"
        vax.dog_id = uuid.uuid4()
        vax.next_due_at = datetime.now(UTC) + timedelta(days=7)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [vax]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_vaccination_renewals({})

        mock_notif.create_notification.assert_called_once()
        call_kwargs = mock_notif.create_notification.call_args[1]
        assert "Rabies" in call_kwargs["message"]
        assert "Vaccination Renewal" in call_kwargs["title"]

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_post_adoption_followups(self, mock_notif_cls, mock_session_factory):
        """Should send follow-ups for adoptions completed 30/90/180 days ago."""
        adoption = MagicMock()
        adoption.adopter_id = uuid.uuid4()
        adoption.dog_id = uuid.uuid4()
        adoption.completed_at = datetime.now(UTC) - timedelta(days=30)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [adoption]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await post_adoption_followups({})

        assert mock_notif.create_notification.call_count >= 1
        call_kwargs = mock_notif.create_notification.call_args[1]
        assert "Day Post-Adoption Follow-Up" in call_kwargs["title"]

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.DonationRepository")
    async def test_process_sponsorship_charges_month_end_rollover(
        self, mock_donation_repo_cls, mock_notif_cls, mock_session_factory
    ):
        """A sponsorship charged on the 31st must roll over to a shorter
        month (e.g. Feb) without raising ValueError."""
        from datetime import date as date_type

        sponsorship = MagicMock()
        sponsorship.id = uuid.uuid4()
        sponsorship.donor_id = uuid.uuid4()
        sponsorship.dog_id = uuid.uuid4()
        sponsorship.monthly_amount = 25
        sponsorship.currency = "USD"
        sponsorship.next_charge_date = date_type(2026, 1, 31)
        sponsorship.donor = MagicMock()
        sponsorship.donor.user_id = uuid.uuid4()

        mock_repo = AsyncMock()
        mock_repo.get_due_sponsorships.return_value = [sponsorship]
        mock_donation_repo_cls.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await process_sponsorship_charges({})

        mock_repo.create_donation.assert_called_once()
        mock_repo.advance_charge_date.assert_called_once()
        next_date = mock_repo.advance_charge_date.call_args[0][1]
        assert next_date == date_type(2026, 2, 28)
