"""Structured logging configuration.

Binds request-scoped context (request_id, user_id, path, method, latency_ms, status_code)
per the AGENTS.md LOGGING CONTRACT. Never log secrets, tokens, or passwords.
"""

import contextlib
import logging
import sys
from typing import Any

import structlog

from pawguard.core.config import get_settings
from pawguard.core.constants import Environment
from pawguard.core.pii import mask_email, mask_full_name, mask_ip, mask_phone

REDACTED_KEYS = {
    "password",
    "hashed_password",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "mfa_secret",
    "authorization",
}

PII_EXEMPT_KEYS = {
    "app_name",
    "module_name",
    "job_name",
    "event_type",
    "logger_name",
    "level",
    "timestamp",
}


def _redact_sensitive(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key.lower() in REDACTED_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def _mask_pii(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if key in PII_EXEMPT_KEYS:
            continue

        if not isinstance(value, (str, int, float)):
            continue

        key_lower = key.lower()
        str_val = str(value)
        if "email" in key_lower:
            event_dict[key] = mask_email(str_val)
        elif "phone" in key_lower or "mobile" in key_lower:
            event_dict[key] = mask_phone(str_val)
        elif "ip_address" in key_lower or key_lower == "ip":
            event_dict[key] = mask_ip(str_val)
        elif any(
            x in key_lower
            for x in (
                "full_name",
                "adopter_name",
                "reporter_name",
                "donor_name",
                "volunteer_name",
                "owner_name",
            )
        ):
            event_dict[key] = mask_full_name(str_val)
        elif any(x in key_lower for x in ("latitude", "longitude", "coords", "coordinates")):
            event_dict[key] = "***MASKED_COORD***"
        elif any(x in key_lower for x in ("address", "street_name", "postal_code")):
            event_dict[key] = "***MASKED_ADDRESS***"

    return event_dict


def configure_logging() -> None:
    settings = get_settings()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_sensitive,
        _mask_pii,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.environment == Environment.LOCAL:
        renderer: Any = structlog.dev.ConsoleRenderer()
    else:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    for noisy_logger in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
