"""Background email jobs. Kept off the request path per TRANSACTION RULES."""

import asyncio
import smtplib
from typing import Any

from arq import Retry

from pawguard.services.email_service import EmailService
from pawguard.workers.jobs.retry import retry_defer

# Transient delivery failures worth retrying: SMTP protocol hiccups, network
# resets, and timeouts. Everything else propagates to the failure tracker.
_TRANSIENT = (smtplib.SMTPException, TimeoutError, ConnectionError)


async def _deliver(ctx: dict[str, Any], *, to: str, subject: str, html_body: str) -> None:
    # SMTP is blocking (smtplib). Run it in a worker thread so the event loop —
    # which also serves the API when running under `pawguard.serve` — never
    # stalls on network I/O (avoids Render health-check timeouts during sends).
    try:
        await asyncio.to_thread(EmailService().send, to=to, subject=subject, html_body=html_body)
    except _TRANSIENT as exc:
        raise Retry(defer=retry_defer(ctx)) from exc


async def send_password_reset_email_job(ctx: dict[str, Any], *, to: str, reset_url: str) -> None:
    html = EmailService().render("password_reset.html", {"reset_url": reset_url})
    await _deliver(ctx, to=to, subject="Reset your PawGuard password", html_body=html)


async def send_email_verification_email_job(
    ctx: dict[str, Any], *, to: str, verify_url: str
) -> None:
    html = EmailService().render("email_verification.html", {"verify_url": verify_url})
    await _deliver(ctx, to=to, subject="Verify your PawGuard email", html_body=html)


async def send_notification_email_job(
    ctx: dict[str, Any], *, to: str, subject: str, body: str
) -> None:
    html = EmailService().render("notification.html", {"subject": subject, "body": body})
    await _deliver(ctx, to=to, subject=subject, html_body=html)
