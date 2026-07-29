"""Background email jobs. Kept off the request path per TRANSACTION RULES."""

from typing import Any

from pawguard.services.email_service import EmailService


async def send_password_reset_email_job(ctx: dict[str, Any], *, to: str, reset_url: str) -> None:
    EmailService().send_password_reset_email(to=to, reset_url=reset_url)


async def send_email_verification_email_job(
    ctx: dict[str, Any], *, to: str, verify_url: str
) -> None:
    EmailService().send_email_verification_email(to=to, verify_url=verify_url)
