"""Tests for scheduled background jobs."""

import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import pawguard
from pawguard.core.payments import PaymentGatewayError
from pawguard.modules.notifications.schemas import NotificationCreate, NotificationSend
from pawguard.workers.jobs.scheduled_jobs import (
    _staff_user_ids,
    check_inventory_expiry,
    check_inventory_low_stock,
    check_vaccination_renewals,
    post_adoption_followups,
    process_sponsorship_charges,
    send_post_service_feedback_surveys,
    send_volunteer_shift_reminders,
)


def test_arq_worker_process_registers_all_models():
    """A fresh interpreter importing ONLY the ARQ worker must be able to
    configure ORM mappers.

    The web app registers every model via api/v1/router.py pulling in each
    router; the worker never did, so the first scheduled job querying a model
    with a string-referenced relationship (e.g. AdoptionApplication.dog ->
    "DogProfile") crashed with InvalidRequestError. Run in a subprocess so
    this is deterministic regardless of what other tests imported first.
    """
    src_dir = str(Path(pawguard.__file__).resolve().parent.parent)
    env = dict(os.environ)
    env["PYTHONPATH"] = src_dir
    code = (
        "import pawguard.workers.arq_worker;"
        "from sqlalchemy.orm import configure_mappers;"
        "configure_mappers();"
        "print('MAPPER_CONFIG_OK')"
    )
    result = subprocess.run(  # noqa: S603 - runs only `sys.executable -c` with a constant script
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(pawguard.__file__).resolve().parent.parent.parent),
        timeout=120,
    )
    assert result.returncode == 0, f"worker boot failed:\n{result.stderr}"
    assert "MAPPER_CONFIG_OK" in result.stdout


class TestScheduledJobs:
    """Test scheduled job functions."""

    def _mock_session(self, items: list[object]) -> AsyncMock:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = items
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        return mock_session

    def _mock_session_factory(self, mock_session: AsyncMock) -> MagicMock:
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_factory

    def _assert_notification_payloads(
        self, mock_notif: AsyncMock, expected_titles: set[str]
    ) -> None:
        assert mock_notif.create_notification.call_count >= 1
        titles = set()
        for call in mock_notif.create_notification.call_args_list:
            payload = call.kwargs["payload"]
            assert isinstance(payload, NotificationCreate)
            assert payload.title in expected_titles
            titles.add(payload.title)
            assert payload.body
        assert titles.issubset(expected_titles)

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.UserRepository")
    async def test_check_inventory_low_stock(
        self, mock_user_repo_cls, mock_notif_cls, mock_session_factory
    ):
        """Should alert staff when stock <= reorder threshold."""
        item = MagicMock()
        item.name = "Dog Food"
        item.quantity = 5
        item.reorder_threshold = 10
        item.unit = "kg"

        mock_session = self._mock_session([item])
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_user_repo = AsyncMock()
        staff_id = uuid.uuid4()
        mock_user_repo.list_staff_user_ids.return_value = [staff_id]
        mock_user_repo_cls.return_value = mock_user_repo

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_inventory_low_stock({})

        self._assert_notification_payloads(mock_notif, {"Inventory Low Stock Alert"})
        payload = mock_notif.create_notification.call_args.kwargs["payload"]
        assert payload.user_id == staff_id
        assert "Dog Food" in payload.body
        assert "low on stock" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.UserRepository")
    async def test_check_inventory_low_stock_no_alerts(
        self, mock_user_repo_cls, mock_notif_cls, mock_session_factory
    ):
        """Should not alert when stock is sufficient."""
        mock_session = self._mock_session([])
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_inventory_low_stock({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.UserRepository")
    async def test_check_inventory_expiry(
        self, mock_user_repo_cls, mock_notif_cls, mock_session_factory
    ):
        """Should alert staff for items expiring within 60 days."""
        from datetime import date as date_type

        item = MagicMock()
        item.name = "Vaccine"
        item.expiry_date = date_type.today() + timedelta(days=10)

        mock_session = self._mock_session([item])
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_user_repo = AsyncMock()
        mock_user_repo.list_staff_user_ids.return_value = [uuid.uuid4()]
        mock_user_repo_cls.return_value = mock_user_repo

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_inventory_expiry({})

        self._assert_notification_payloads(mock_notif, {"Inventory Expiry Warning"})
        payload = mock_notif.create_notification.call_args.kwargs["payload"]
        assert "Vaccine" in payload.body
        assert "expires" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.UserRepository")
    async def test_check_vaccination_renewals(
        self, mock_user_repo_cls, mock_notif_cls, mock_session_factory
    ):
        """Should remind staff for vaccinations due within 14 days."""
        vax = MagicMock()
        vax.vaccine_name = "Rabies"
        vax.dog_id = uuid.uuid4()
        vax.next_due_at = datetime.now(UTC) + timedelta(days=7)

        mock_session = self._mock_session([vax])
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_user_repo = AsyncMock()
        mock_user_repo.list_staff_user_ids.return_value = [uuid.uuid4()]
        mock_user_repo_cls.return_value = mock_user_repo

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_vaccination_renewals({})

        self._assert_notification_payloads(mock_notif, {"Vaccination Renewal Reminder"})
        payload = mock_notif.create_notification.call_args.kwargs["payload"]
        assert "Rabies" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_post_adoption_followups(self, mock_notif_cls, mock_session_factory):
        """Should send follow-ups for adoptions completed 30/90/180 days ago."""
        adopter_id = uuid.uuid4()
        adoption = MagicMock()
        adoption.adopter_id = adopter_id
        adoption.dog_id = uuid.uuid4()
        adoption.completed_at = datetime.now(UTC) - timedelta(days=30)

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        adoption_result = MagicMock()
        adoption_result.scalars.return_value.all.return_value = [adoption]

        mock_session = AsyncMock()
        mock_session.execute.return_value = adoption_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await post_adoption_followups({})

        assert mock_notif.send_notification.call_count >= 1
        payload = mock_notif.send_notification.call_args.kwargs["payload"]
        assert isinstance(payload, NotificationSend)
        assert payload.user_id == adopter_id
        assert "Day Post-Adoption Follow-Up" in payload.title

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_staff_alert_jobs_skip_when_no_staff_match(
        self, mock_notif_cls, mock_session_factory
    ):
        """A system alert with no eligible staff recipient should create nothing
        (Notification.user_id is NOT NULL, so there is no 'system' recipient)."""
        item = MagicMock()
        item.name = "Dog Food"
        item.quantity = 1
        item.reorder_threshold = 5
        item.unit = "kg"

        item_result = MagicMock()
        item_result.scalars.return_value.all.return_value = [item]
        no_staff_result = MagicMock()
        no_staff_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [item_result, no_staff_result]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await check_inventory_low_stock({})

        mock_notif.create_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_staff_user_ids_returns_eligible_permission_holders(self):
        """_staff_user_ids queries active, non-deleted users holding the
        permission and returns their ids."""
        staff_user_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [staff_user_id]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        result = await _staff_user_ids(mock_session, "inventory:read")

        assert result == [staff_user_id]
        stmt = mock_session.execute.call_args[0][0]
        rendered = str(stmt)
        # The query must walk user -> roles -> role_permissions -> permissions
        assert "users" in rendered
        assert "user_roles" in rendered
        assert "role_permissions" in rendered
        assert "permissions" in rendered

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_send_post_service_feedback_surveys(self, mock_notif_cls, mock_session_factory):
        """Completed adoptions (7-14 days old) with no feedback and no prior
        survey prompt should get a feedback_survey notification to the adopter."""
        adoption = MagicMock()
        adoption.id = uuid.uuid4()
        adoption.adopter_id = uuid.uuid4()
        adoption.dog_id = uuid.uuid4()
        adoption.completed_at = datetime.now(UTC) - timedelta(days=10)

        adoptions_result = MagicMock()
        adoptions_result.scalars.return_value.all.return_value = [adoption]
        no_feedback_result = MagicMock()
        no_feedback_result.scalars.return_value.all.return_value = []
        no_prior_result = MagicMock()
        no_prior_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            adoptions_result,
            no_feedback_result,
            no_prior_result,
        ]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await send_post_service_feedback_surveys({})

        assert mock_notif.send_notification.call_count == 1
        payload = mock_notif.send_notification.call_args.kwargs["payload"]
        assert isinstance(payload, NotificationSend)
        assert payload.user_id == adoption.adopter_id
        assert payload.notification_type == "feedback_survey"
        assert str(adoption.id) in payload.action_url
        assert "rate" in payload.body

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_send_post_service_feedback_surveys_skips_submitted_and_prior(
        self, mock_notif_cls, mock_session_factory
    ):
        """Adoptions that already have feedback, or already received a survey,
        must not be prompted again."""
        adoption_with_feedback = MagicMock()
        adoption_with_feedback.id = uuid.uuid4()
        adoption_with_feedback.adopter_id = uuid.uuid4()
        adoption_with_feedback.dog_id = uuid.uuid4()

        adoption_with_prior = MagicMock()
        adoption_with_prior.id = uuid.uuid4()
        adoption_with_prior.adopter_id = uuid.uuid4()
        adoption_with_prior.dog_id = uuid.uuid4()

        adoption_new = MagicMock()
        adoption_new.id = uuid.uuid4()
        adoption_new.adopter_id = uuid.uuid4()
        adoption_new.dog_id = uuid.uuid4()

        adoptions_result = MagicMock()
        adoptions_result.scalars.return_value.all.return_value = [
            adoption_with_feedback,
            adoption_with_prior,
            adoption_new,
        ]
        feedback_result = MagicMock()
        feedback_result.scalars.return_value.all.return_value = [adoption_with_feedback.id]
        prior_result = MagicMock()
        prior_result.scalars.return_value.all.return_value = [
            f"/api/v1/grievance/feedback?adoption_application_id={adoption_with_prior.id}"
        ]

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            adoptions_result,
            feedback_result,
            prior_result,
        ]
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await send_post_service_feedback_surveys({})

        assert mock_notif.send_notification.call_count == 1
        payload = mock_notif.send_notification.call_args.kwargs["payload"]
        assert payload.user_id == adoption_new.adopter_id

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    async def test_send_post_service_feedback_surveys_no_pending(
        self, mock_notif_cls, mock_session_factory
    ):
        """No completed adoptions in the window should create no notifications."""
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = empty_result
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        await send_post_service_feedback_surveys({})

        mock_notif.send_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.get_payment_gateway")
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.DonationRepository")
    async def test_process_sponsorship_charges_month_end_rollover(
        self, mock_donation_repo_cls, mock_notif_cls, mock_session_factory, mock_gateway_factory
    ):
        """A sponsorship charged on the 31st must roll over to a shorter
        month (e.g. Feb) without raising ValueError, and must be recorded
        PENDING (never fabricated SUCCESS) when no gateway is configured."""
        from datetime import date as date_type

        mock_gateway_factory.side_effect = PaymentGatewayError("not configured")

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
        mock_repo.has_pending_donation_for_sponsorship.return_value = False
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

        payload = mock_notif.send_notification.call_args.kwargs["payload"]
        assert isinstance(payload, NotificationSend)
        assert payload.notification_type == "sponsorship_charge"

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.VolunteerRepository")
    async def test_send_volunteer_shift_reminders_eligible_shift(
        self, mock_repo_cls, mock_notif_cls, mock_session_factory
    ):
        """A claimed attendance whose shift starts within the window gets
        reminded, and the attendance is flagged so it won't be reminded
        again."""
        attendance_id = uuid.uuid4()
        volunteer_user_id = uuid.uuid4()
        shift = MagicMock(role_name="Dog Walking", start_at=datetime.now(UTC) + timedelta(hours=5))
        user = MagicMock(email="vol@example.com")
        volunteer = MagicMock(user_id=volunteer_user_id, user=user)
        attendance = MagicMock(
            id=attendance_id, shift=shift, volunteer=volunteer, reminder_sent_at=None
        )

        mock_repo = AsyncMock()
        mock_repo.list_claimed_attendance_due_for_reminder.return_value = [attendance]
        mock_repo_cls.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        sent = await send_volunteer_shift_reminders({})

        assert sent == 1
        mock_notif.send_notification.assert_awaited_once()
        payload = mock_notif.send_notification.call_args.kwargs["payload"]
        assert isinstance(payload, NotificationSend)
        assert payload.notification_type == "volunteer_shift_reminder"
        assert payload.user_id == volunteer_user_id
        # The dedup flag must actually be set on the record that was sent.
        assert attendance.reminder_sent_at is not None
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.VolunteerRepository")
    async def test_send_volunteer_shift_reminders_none_due(
        self, mock_repo_cls, mock_notif_cls, mock_session_factory
    ):
        """No claimed attendance in the window (already reminded, cancelled,
        checked-in, or for an inactive volunteer — all filtered by the
        repository query itself) means no notification is sent."""
        mock_repo = AsyncMock()
        mock_repo.list_claimed_attendance_due_for_reminder.return_value = []
        mock_repo_cls.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif_cls.return_value = mock_notif

        sent = await send_volunteer_shift_reminders({})

        assert sent == 0
        mock_notif.send_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal")
    @patch("pawguard.workers.jobs.scheduled_jobs.NotificationService")
    @patch("pawguard.workers.jobs.scheduled_jobs.VolunteerRepository")
    async def test_send_volunteer_shift_reminders_failure_does_not_mark_sent(
        self, mock_repo_cls, mock_notif_cls, mock_session_factory
    ):
        """A notification-send failure for one attendance must not crash the
        job, must not be counted as sent, and must leave `reminder_sent_at`
        unset so the next run retries it."""
        attendance_id = uuid.uuid4()
        shift = MagicMock(role_name="Dog Walking", start_at=datetime.now(UTC) + timedelta(hours=5))
        volunteer = MagicMock(user_id=uuid.uuid4(), user=MagicMock(email="vol@example.com"))
        attendance = MagicMock(
            id=attendance_id, shift=shift, volunteer=volunteer, reminder_sent_at=None
        )

        mock_repo = AsyncMock()
        mock_repo.list_claimed_attendance_due_for_reminder.return_value = [attendance]
        mock_repo_cls.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_notif = AsyncMock()
        mock_notif.send_notification.side_effect = RuntimeError("email provider down")
        mock_notif_cls.return_value = mock_notif

        sent = await send_volunteer_shift_reminders({})

        assert sent == 0
        assert attendance.reminder_sent_at is None

    @pytest.mark.asyncio
    async def test_arq_worker_startup_preserves_in_progress_locks(self):
        """Worker startup must NOT purge arq:in-progress:* keys so sibling workers are protected."""
        from pawguard.workers.arq_worker import startup

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        ctx = {"redis": mock_redis}

        await startup(ctx)

        mock_redis.delete.assert_not_called()
