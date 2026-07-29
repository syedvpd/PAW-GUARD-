"""Cross-cutting HTTP middleware: request ID, timing/logging, security headers."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pawguard.core.constants import REQUEST_ID_HEADER
from pawguard.core.logging import get_logger

logger = get_logger(__name__)

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID and binds structlog context for the LOGGING CONTRACT."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs one structured line per request: method, path, status, latency, user."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        user_id = getattr(request.state, "user_id", None)
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            module=request.url.path.strip("/").split("/")[:3],
            status_code=response.status_code,
            latency_ms=latency_ms,
            user_id=str(user_id) if user_id else None,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies baseline security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
