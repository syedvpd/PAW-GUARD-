"""Jinja2-templated transactional email rendering + SMTP delivery.

Per AGENTS.md TRANSACTION RULES, this is only ever invoked from an ARQ job
(`workers/jobs/email_jobs.py`), never inline within an HTTP request/DB transaction.
"""

import smtplib
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pawguard.core.config import get_settings
from pawguard.core.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


class EmailService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def render(self, template_name: str, context: dict[str, object]) -> str:
        template = _jinja_env.get_template(template_name)
        return template.render(**context)

    def send(self, *, to: str, subject: str, html_body: str) -> None:
        message = EmailMessage()
        message["From"] = self._settings.mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content("This email requires an HTML-capable client.")
        message.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(self._settings.mail_host, self._settings.mail_port) as smtp:
            if self._settings.mail_use_tls:
                smtp.starttls()
            if self._settings.mail_username:
                smtp.login(self._settings.mail_username, self._settings.mail_password)
            smtp.send_message(message)

        logger.info("email_sent", to=to, subject=subject)

    def send_password_reset_email(self, *, to: str, reset_url: str) -> None:
        html = self.render("password_reset.html", {"reset_url": reset_url})
        self.send(to=to, subject="Reset your PawGuard password", html_body=html)

    def send_email_verification_email(self, *, to: str, verify_url: str) -> None:
        html = self.render("email_verification.html", {"verify_url": verify_url})
        self.send(to=to, subject="Verify your PawGuard email", html_body=html)
