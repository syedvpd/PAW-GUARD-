"""Cross-cutting HTTP middleware: request ID, timing/logging, security headers, body size."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pawguard.core.config import get_settings
from pawguard.core.constants import REQUEST_ID_HEADER
from pawguard.core.logging import get_logger
from pawguard.core.metrics import increment_counter, observe_histogram

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
        labels = {
            "method": request.method,
            "path": request.url.path,
            "status": str(response.status_code),
        }
        increment_counter("http_requests_total", labels)
        observe_histogram("http_request_duration_ms", latency_ms, labels)

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


# Paths whose HTML pages need to load JS/CSS from a CDN (Swagger UI / ReDoc assets).
# Everything else on the API keeps the strict, CDN-free CSP.
_DOCS_PATHS = ("/docs", "/redoc")

_STRICT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies baseline security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        if request.url.path in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = _DOCS_CSP
        else:
            response.headers["Content-Security-Policy"] = _STRICT_CSP

        if request.url.path.startswith(("/api/", "/auth/")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


class RequestBodySizeMiddleware(BaseHTTPMiddleware):
    """Rejects requests with body exceeding the configured max size."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            size = int(content_length)
            max_size = get_settings().max_request_body_size
            if size > max_size:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={"success": False, "error": "Request body too large."},
                )
        return await call_next(request)