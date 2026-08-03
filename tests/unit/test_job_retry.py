"""Tests for ARQ job retry/backoff on transient failures."""

import smtplib
from unittest.mock import patch

import pytest
from arq import Retry
from sqlalchemy.exc import OperationalError

from pawguard.workers.jobs.email_jobs import (
    send_notification_email_job,
    send_password_reset_email_job,
)
from pawguard.workers.jobs.scheduled_jobs import process_sponsorship_charges


class TestEmailJobRetry:
    @pytest.mark.asyncio
    async def test_transient_smtp_error_raises_retry(self) -> None:
        with patch("pawguard.workers.jobs.email_jobs.EmailService") as mock_svc:
            mock_svc.return_value.send.side_effect = smtplib.SMTPConnectError(1, "down")
            with pytest.raises(Retry) as exc_info:
                await send_password_reset_email_job(
                    {"job_try": 2}, to="a@b.com", reset_url="https://x"
                )
            assert exc_info.value.defer_score == 60_000

    @pytest.mark.asyncio
    async def test_timeout_raises_retry(self) -> None:
        with patch("pawguard.workers.jobs.email_jobs.EmailService") as mock_svc:
            mock_svc.return_value.send.side_effect = TimeoutError("slow")
            with pytest.raises(Retry):
                await send_notification_email_job(
                    {"job_try": 1}, to="a@b.com", subject="s", body="b"
                )

    @pytest.mark.asyncio
    async def test_hard_error_propagates(self) -> None:
        with patch("pawguard.workers.jobs.email_jobs.EmailService") as mock_svc:
            mock_svc.return_value.send.side_effect = ValueError("bad recipient")
            with pytest.raises(ValueError):
                await send_notification_email_job(
                    {"job_try": 1}, to="a@b.com", subject="s", body="b"
                )

    @pytest.mark.asyncio
    async def test_success_does_not_raise(self) -> None:
        with patch("pawguard.workers.jobs.email_jobs.EmailService") as mock_svc:
            await send_notification_email_job(
                {"job_try": 1}, to="a@b.com", subject="s", body="b"
            )
            mock_svc.return_value.send.assert_called_once()


class TestSponsorshipJobRetry:
    @pytest.mark.asyncio
    async def test_transient_db_error_raises_retry(self) -> None:
        with patch(
            "pawguard.workers.jobs.scheduled_jobs._run_sponsorship_charges",
            side_effect=OperationalError("stmt", {}, Exception("conn lost")),
        ):
            with pytest.raises(Retry) as exc_info:
                await process_sponsorship_charges({"job_try": 3})
            assert exc_info.value.defer_score == 120_000

    @pytest.mark.asyncio
    async def test_success_does_not_raise(self) -> None:
        with patch("pawguard.workers.jobs.scheduled_jobs._run_sponsorship_charges") as mock_run:
            await process_sponsorship_charges({"job_try": 1})
            mock_run.assert_awaited_once()
