"""Jinja2-templated transactional email rendering + delivery.

Delivery strategy (in order):
1. Brevo HTTP API (port 443) - works on all cloud platforms, including Render's
   free tier where outbound SMTP ports (587/465) may be blocked.
2. SMTP fallback (port 587) - used when no Brevo API key is configured.

Per AGENTS.md TRANSACTION RULES, this is only ever invoked from an ARQ job
(`workers/jobs/email_jobs.py`), never inline within an HTTP request/DB transaction.
"""

import json
import smtplib
import ssl
import urllib.error
import urllib.request
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
        """Deliver an HTML email.

        Prefers the Brevo HTTP API (port 443, always reachable) when an API key
        is configured, because many cloud platforms block outbound SMTP ports.
        Falls back to SMTP when no API key is set.
        """
        if self._settings.brevo_api_key:
            self._send_via_brevo_api(to=to, subject=subject, html_body=html_body)
        else:
            self._send_via_smtp(to=to, subject=subject, html_body=html_body)

    def _send_via_brevo_api(self, *, to: str, subject: str, html_body: str) -> None:
        import time

        from pawguard.core.metrics import track_outbound_request

        start = time.perf_counter()
        payload = json.dumps(
            {
                "sender": {"name": "PawGuard", "email": self._settings.mail_from_email},
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": html_body,
            }
        ).encode()

        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers={
                "api-key": self._settings.brevo_api_key,
                "Content-Type": "application/json",
                "accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed https Brevo endpoint
                status = resp.status
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="brevo",
                operation="send_email_api",
                request_bytes=len(payload),
                response_bytes=100,
                duration_ms=duration_ms,
                status="success",
            )
        except urllib.error.HTTPError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="brevo",
                operation="send_email_api",
                request_bytes=len(payload),
                response_bytes=0,
                duration_ms=duration_ms,
                status="failed",
            )
            body = exc.read().decode(errors="replace")[:300]
            logger.error("brevo_api_error", to=to, subject=subject, status=exc.code, body=body)
            raise
        except urllib.error.URLError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="brevo",
                operation="send_email_api",
                request_bytes=len(payload),
                response_bytes=0,
                duration_ms=duration_ms,
                status="failed",
            )
            logger.error("brevo_api_network_error", to=to, subject=subject, error=str(exc.reason))
            raise

        logger.info("email_sent", to=to, subject=subject, method="brevo_api", status=status)

    def _send_via_smtp(self, *, to: str, subject: str, html_body: str) -> None:
        import time

        from pawguard.core.metrics import track_outbound_request

        start = time.perf_counter()
        message = EmailMessage()
        message["From"] = self._settings.mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content("This email requires an HTML-capable client.")
        message.add_alternative(html_body, subtype="html")
        msg_bytes = len(message.as_bytes())

        smtp_kwargs: dict[str, object] = {
            "host": self._settings.mail_host,
            "port": self._settings.mail_port,
            "timeout": 10,
        }
        try:
            with smtplib.SMTP(**smtp_kwargs) as smtp:
                if self._settings.mail_use_ssl:
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(
                        self._settings.mail_host,
                        self._settings.mail_port,
                        context=context,
                        timeout=10,
                    ) as smtp_ssl:
                        if self._settings.mail_username:
                            smtp_ssl.login(
                                self._settings.mail_username, self._settings.mail_password
                            )
                        smtp_ssl.send_message(message)
                else:
                    if self._settings.mail_use_tls:
                        smtp.starttls()
                    if self._settings.mail_username:
                        smtp.login(self._settings.mail_username, self._settings.mail_password)
                    smtp.send_message(message)
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="smtp",
                operation="send_email_smtp",
                request_bytes=msg_bytes,
                response_bytes=0,
                duration_ms=duration_ms,
                status="success",
            )
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            track_outbound_request(
                destination="smtp",
                operation="send_email_smtp",
                request_bytes=msg_bytes,
                response_bytes=0,
                duration_ms=duration_ms,
                status="failed",
            )
            raise

        logger.info("email_sent", to=to, subject=subject, method="smtp")

    def send_password_reset_email(self, *, to: str, reset_url: str) -> None:
        html = self.render("password_reset.html", {"reset_url": reset_url})
        self.send(to=to, subject="Reset your PawGuard password", html_body=html)

    def send_email_verification_email(self, *, to: str, verify_url: str) -> None:
        html = self.render("email_verification.html", {"verify_url": verify_url})
        self.send(to=to, subject="Verify your PawGuard email", html_body=html)
