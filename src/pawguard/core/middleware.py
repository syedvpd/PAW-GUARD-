"""Cross-cutting HTTP middleware: request ID, timing/logging, security headers, body size."""

import re
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
from pawguard.core.metrics import (
    dec_gauge,
    inc_gauge,
    increment_counter,
    observe_histogram,
)

logger = get_logger(__name__)

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]

TRACE_ID_HEADER = "x-trace-id"
SPAN_ID_HEADER = "x-span-id"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns request_id, trace_id, and span_id, binding context for structured logging and distributed tracing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_req_id = request.headers.get("x-request-id", request.headers.get(REQUEST_ID_HEADER, ""))
        if raw_req_id and re.match(r"^[a-zA-Z0-9_\-\.]{1,64}$", raw_req_id):
            request_id = raw_req_id
        else:
            request_id = f"req_{uuid.uuid4().hex[:12]}"

        trace_id = request.headers.get(
            "x-trace-id", request.headers.get("traceparent", str(uuid.uuid4().hex))
        )
        span_id = request.headers.get("x-span-id", str(uuid.uuid4().hex[:16]))

        request.state.request_id = request_id
        request.state.trace_id = trace_id
        request.state.span_id = span_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            trace_id=trace_id,
            span_id=span_id,
        )

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["x-request-id"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Span-ID"] = span_id
        return response


_UUID_REGEX = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _resolve_route_path(request: Request) -> str:
    """Resolve low-cardinality route template (e.g. /api/v1/dogs/{id}) to prevent metric explosion."""
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return str(route.path)
    return _UUID_REGEX.sub("{id}", request.url.path)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs structured metrics & RED telemetry per request: rate, error rate, duration, and in-flight gauge."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        inc_gauge("http_requests_in_flight", {"method": method})
        start = time.perf_counter()

        try:
            response = await call_next(request)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = response.status_code
            status_class = f"{status_code // 100}xx"
            route_path = _resolve_route_path(request)

            red_labels = {
                "method": method,
                "route": route_path,
                "status_class": status_class,
                "status": str(status_code),
            }
            increment_counter("http_requests_total", red_labels)

            content_length = response.headers.get("content-length")
            if content_length:
                resp_bytes = int(content_length)
            elif hasattr(response, "body"):
                resp_bytes = len(response.body)
            else:
                resp_bytes = 0

            if resp_bytes > 0:
                increment_counter(
                    "pawguard_http_response_bytes_total",
                    {"method": method, "route": route_path, "status": str(status_code)},
                    resp_bytes,
                )

            if status_code >= 400:
                increment_counter(
                    "http_requests_errors_total",
                    {"method": method, "route": route_path, "status_class": status_class},
                )
            if status_code in (408, 504):
                increment_counter(
                    "http_request_timeouts_total",
                    {"method": method, "route": route_path},
                )

            observe_histogram(
                "http_request_duration_ms",
                latency_ms,
                {"method": method, "route": route_path, "status_class": status_class},
            )

            user_id = getattr(request.state, "user_id", None)
            logger.info(
                "request_completed",
                method=method,
                path=request.url.path,
                route=route_path,
                module=request.url.path.strip("/").split("/")[:3],
                status_code=status_code,
                status_class=status_class,
                latency_ms=latency_ms,
                user_id=str(user_id) if user_id else None,
            )
            return response
        finally:
            dec_gauge("http_requests_in_flight", {"method": method})


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

        if request.url.path.startswith(
            (
                "/api/v1/portal/",
                "/api/v1/storage/files/download",
                "/api/v1/storage/files/view",
            )
        ):
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = (
                    "public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400"
                )
        elif request.url.path.startswith(("/api/", "/auth/")):
            if "Cache-Control" not in response.headers:
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
