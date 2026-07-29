"""Structured logging configuration.

Binds request-scoped context (request_id, user_id, path, method, latency_ms, status_code)
per the AGENTS.md LOGGING CONTRACT. Never log secrets, tokens, or passwords.
"""

import logging
import sys
from typing import Any

import structlog

from pawguard.core.config import get_settings
from pawguard.core.constants import Environment

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


def _redact_sensitive(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key.lower() in REDACTED_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def configure_logging() -> None:
    settings = get_settings()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_sensitive,
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
