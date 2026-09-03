"""Application exception hierarchy and FastAPI exception handlers.

Never leak SQL errors, stack traces, or framework internals to clients — every AppException
carries a stable machine-readable `code`, `category`, `layer`, and a safe client-facing `message`.
"""

import re
import uuid
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import (
    DataError,
    DisconnectionError,
    IntegrityError,
    ProgrammingError,
    SQLAlchemyError,
)
from sqlalchemy.exc import (
    TimeoutError as SATimeoutError,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from pawguard.core.logging import get_logger
from pawguard.core.responses import error_envelope

logger = get_logger(__name__)


class ErrorCategory(StrEnum):
    ROUTING = "ROUTING"
    RESOURCE = "RESOURCE"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    VALIDATION = "VALIDATION"
    CONFLICT = "CONFLICT"
    DATABASE = "DATABASE"
    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    RATE_LIMIT = "RATE_LIMIT"
    UPSTREAM_SERVICE = "UPSTREAM_SERVICE"
    SYSTEM = "SYSTEM"


class ErrorLayer(StrEnum):
    ROUTER = "ROUTER"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    VALIDATION = "VALIDATION"
    CONTROLLER = "CONTROLLER"
    SERVICE = "SERVICE"
    DATABASE = "DATABASE"
    UPSTREAM_SERVICE = "UPSTREAM_SERVICE"
    SERIALIZATION = "SERIALIZATION"
    SYSTEM = "SYSTEM"


class AppException(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "APP_ERROR"
    category: str = ErrorCategory.BUSINESS_LOGIC
    layer: str = ErrorLayer.SERVICE

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        category: str | None = None,
        layer: str | None = None,
        details: Any = None,
    ) -> None:
        self.message = message
        self.code = code or self.code
        self.category = category or self.category
        self.layer = layer or self.layer
        self.details = details
        super().__init__(message)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "RESOURCE_NOT_FOUND"
    category = ErrorCategory.RESOURCE
    layer = ErrorLayer.SERVICE


class RouteNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "ROUTE_NOT_FOUND"
    category = ErrorCategory.ROUTING
    layer = ErrorLayer.ROUTER


class ValidationFailedError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "VALIDATION_FAILED"
    category = ErrorCategory.VALIDATION
    layer = ErrorLayer.VALIDATION


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    category = ErrorCategory.CONFLICT
    layer = ErrorLayer.SERVICE


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTHENTICATION_REQUIRED"
    category = ErrorCategory.AUTHENTICATION
    layer = ErrorLayer.AUTHENTICATION


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "AUTHORIZATION_FAILED"
    category = ErrorCategory.AUTHORIZATION
    layer = ErrorLayer.AUTHORIZATION


class TooManyRequestsError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMIT_EXCEEDED"
    category = ErrorCategory.RATE_LIMIT
    layer = ErrorLayer.ROUTER


class DatabaseError(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "DATABASE_QUERY_FAILED"
    category = ErrorCategory.DATABASE
    layer = ErrorLayer.DATABASE


class DatabaseConnectionError(DatabaseError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "DATABASE_CONNECTION_FAILED"
    category = ErrorCategory.DATABASE
    layer = ErrorLayer.DATABASE


class DatabaseSchemaError(DatabaseError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "DATABASE_SCHEMA_ERROR"
    category = ErrorCategory.DATABASE
    layer = ErrorLayer.DATABASE


class DatabaseConstraintError(ConflictError):
    status_code = status.HTTP_409_CONFLICT
    code = "DATABASE_CONSTRAINT_FAILED"
    category = ErrorCategory.DATABASE
    layer = ErrorLayer.DATABASE


class UpstreamServiceError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "UPSTREAM_SERVICE_FAILED"
    category = ErrorCategory.UPSTREAM_SERVICE
    layer = ErrorLayer.UPSTREAM_SERVICE


def parse_enum[EnumT: StrEnum](
    enum_cls: type[EnumT], value: str, *, field_name: str = "status"
) -> EnumT:
    """Converts a raw string into a StrEnum member, raising a clean 422
    instead of letting the constructor's bare ValueError fall through to
    the generic 500 handler.
    """
    try:
        return enum_cls(value)
    except ValueError as exc:
        valid = ", ".join(m.value for m in enum_cls)
        raise ValidationFailedError(
            f"Invalid {field_name} '{value}'. Must be one of: {valid}."
        ) from exc


def _get_request_id(request: Request) -> str:
    """Extract or generate a validated, safe correlation request ID."""
    req_id = getattr(request.state, "request_id", None)
    if not req_id:
        client_header = request.headers.get("x-request-id", "")
        if client_header and re.match(r"^[a-zA-Z0-9_\-\.]{1,64}$", client_header):
            req_id = client_header
        else:
            req_id = f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id
    return req_id


def _sanitize_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Ensure all error detail values are JSON-serializable."""
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        item: dict[str, Any] = {}
        for key, value in err.items():
            if isinstance(value, dict):
                item[key] = {
                    k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                    for k, v in value.items()
                }
            else:
                item[key] = value
        sanitized.append(item)
    return sanitized


ERR_PATTERNS = ("MissingGreenlet", "Error extracting attribute", "get_attribute_error")
PREFIX_PATTERNS = ("1 validation error for", "Validation error for")


def clean_error_message(msg: str) -> str:
    """Format validation and exception messages to be concise, clean (1-2 lines),
    and production-ready per enterprise API design standards.
    """
    if not msg:
        return "Invalid request payload or schema validation error."

    if any(p in msg for p in ERR_PATTERNS):
        return "Internal processing error: database entity relations failed to load during serialization."

    if "For further information visit" in msg:
        msg = msg.split("For further information visit")[0]
    msg = re.sub(r"\[type=[a-z0-9_.]+\]", "", msg)
    if "(Background on this error at:" in msg:
        msg = msg.split("(Background on this error at:")[0]

    lines = [line.strip() for line in msg.splitlines() if line.strip()]
    if not lines:
        return "Request validation failed."

    if len(lines) == 1:
        return lines[0]

    cleaned_lines = [line for line in lines if not line.startswith(PREFIX_PATTERNS)]
    return " | ".join(cleaned_lines) if cleaned_lines else lines[0]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.info(
            "app_exception",
            code=exc.code,
            category=exc.category,
            layer=exc.layer,
            path=request.url.path,
            method=request.method,
            status_code=exc.status_code,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(
                code=exc.code,
                category=exc.category,
                layer=exc.layer,
                message=clean_error_message(exc.message),
                details=exc.details,
                endpoint=request.url.path,
                method=request.method,
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _get_request_id(request)
        err_details = _sanitize_errors(exc.errors())
        first_msg = "Request validation failed."
        if err_details and isinstance(err_details, list) and len(err_details) > 0:
            first_err = err_details[0]
            loc_str = " -> ".join(str(loc) for loc in first_err.get("loc", []) if loc != "body")
            msg_str = first_err.get("msg", "")
            if loc_str and msg_str:
                first_msg = f"Validation failed for '{loc_str}': {msg_str}"
            elif msg_str:
                first_msg = f"Validation failed: {msg_str}"

        logger.info(
            "request_validation_failed",
            path=request.url.path,
            method=request.method,
            error=first_msg,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_envelope(
                code="VALIDATION_ERROR",
                category=ErrorCategory.VALIDATION,
                layer=ErrorLayer.VALIDATION,
                message=clean_error_message(first_msg),
                details=err_details,
                endpoint=request.url.path,
                method=request.method,
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(ResponseValidationError)
    async def response_validation_exception_handler(
        request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.error(
            "response_validation_error",
            path=request.url.path,
            method=request.method,
            request_id=request_id,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(
                code="RESPONSE_SERIALIZATION_FAILED",
                category=ErrorCategory.SYSTEM,
                layer=ErrorLayer.SERIALIZATION,
                message="An internal error occurred while formatting response data model.",
                details="The backend entity structure did not conform to the expected response schema.",
                endpoint=request.url.path,
                method=request.method,
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(ValueError)
    async def value_exception_handler(request: Request, exc: ValueError) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.info(
            "value_error",
            path=request.url.path,
            method=request.method,
            message=str(exc),
            request_id=request_id,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_envelope(
                code="VALIDATION_ERROR",
                category=ErrorCategory.VALIDATION,
                layer=ErrorLayer.VALIDATION,
                message=clean_error_message(str(exc)) or "Invalid value provided.",
                endpoint=request.url.path,
                method=request.method,
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = _get_request_id(request)
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "ROUTE_NOT_FOUND"
            category = ErrorCategory.ROUTING
            layer = ErrorLayer.ROUTER
            message = (
                f"The requested API route '{request.method} {request.url.path}' "
                "does not exist on this server. Check the URL path and HTTP method."
            )
            details = "Verify API endpoint route prefix, path parameters, and HTTP verb."
        elif exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            code = "METHOD_NOT_ALLOWED"
            category = ErrorCategory.ROUTING
            layer = ErrorLayer.ROUTER
            message = f"HTTP method '{request.method}' is not allowed for '{request.url.path}'."
            details = "Check the allowed HTTP methods for this endpoint."
        elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
            code = "AUTHENTICATION_REQUIRED"
            category = ErrorCategory.AUTHENTICATION
            layer = ErrorLayer.AUTHENTICATION
            message = (
                str(exc.detail)
                if exc.detail and exc.detail != "Unauthorized"
                else "Authentication is required to access this endpoint."
            )
            details = "Provide a valid Bearer token or active session cookie."
        elif exc.status_code == status.HTTP_403_FORBIDDEN:
            code = "AUTHORIZATION_FAILED"
            category = ErrorCategory.AUTHORIZATION
            layer = ErrorLayer.AUTHORIZATION
            message = (
                str(exc.detail)
                if exc.detail and exc.detail != "Forbidden"
                else "You do not have permission to perform this action."
            )
            details = "User role lacks required permission scope."
        else:
            code = "HTTP_ERROR"
            category = ErrorCategory.SYSTEM
            layer = ErrorLayer.ROUTER
            message = str(exc.detail)
            details = None

        logger.warning(
            "http_exception",
            status_code=exc.status_code,
            code=code,
            category=category,
            layer=layer,
            path=request.url.path,
            method=request.method,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(
                code=code,
                category=category,
                layer=layer,
                message=clean_error_message(message),
                details=details,
                endpoint=request.url.path,
                method=request.method,
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        request_id = _get_request_id(request)
        err_msg = str(exc).lower()
        orig_msg = str(getattr(exc, "orig", ""))
        orig_lower = orig_msg.lower()

        logger.error(
            "database_error",
            path=request.url.path,
            method=request.method,
            exception_type=type(exc).__name__,
            request_id=request_id,
            exc_info=exc,
        )

        # 1. Connection / Network / Timeout failures
        connection_keywords = (
            "connection refused",
            "could not connect",
            "connection closed",
            "timeout",
            "server closed the connection",
            "cannotconnectnowerror",
            "is not accepting connections",
            "connection reset",
            "broken pipe",
        )
        if isinstance(exc, (DisconnectionError, SATimeoutError)) or any(
            k in err_msg or k in orig_lower for k in connection_keywords
        ):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=error_envelope(
                    code="DATABASE_CONNECTION_FAILED",
                    category=ErrorCategory.DATABASE,
                    layer=ErrorLayer.DATABASE,
                    message="The database service is currently unavailable or unreachable.",
                    details="Database connection failed or timed out during query execution.",
                    endpoint=request.url.path,
                    method=request.method,
                    request_id=request_id,
                ),
                headers={"X-Request-ID": request_id},
            )

        # 2. Schema / Migration / Undefined relation / column failures
        schema_keywords = (
            "does not exist",
            "undefined table",
            "undefined column",
            "undefined_table",
            "undefined_column",
            "no such table",
            "no such column",
            "schema mismatch",
            "undefinedobject",
        )
        if isinstance(exc, ProgrammingError) or any(
            k in err_msg or k in orig_lower for k in schema_keywords
        ):
            if any(k in err_msg or k in orig_lower for k in schema_keywords):
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content=error_envelope(
                        code="DATABASE_SCHEMA_ERROR",
                        category=ErrorCategory.DATABASE,
                        layer=ErrorLayer.DATABASE,
                        message="A database schema mismatch or pending migration issue occurred.",
                        details="The database structure does not match expected entity definitions.",
                        endpoint=request.url.path,
                        method=request.method,
                        request_id=request_id,
                    ),
                    headers={"X-Request-ID": request_id},
                )

        # 3. Integrity Violations (Unique, FK, Check, Not Null)
        if isinstance(exc, IntegrityError) or "integrityerror" in err_msg:
            unique_keywords = ("unique", "duplicate key", "already exists", "unique_violation")
            if any(k in err_msg or k in orig_lower for k in unique_keywords):
                detail_msg = "A record with this unique identifier or key already exists."
                if "Key (" in orig_msg:
                    key_part = orig_msg.split("Key (")[-1].split(")")[0]
                    if key_part:
                        detail_msg = f"A record with {key_part} already exists."
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=error_envelope(
                        code="DUPLICATE_RESOURCE",
                        category=ErrorCategory.DATABASE,
                        layer=ErrorLayer.DATABASE,
                        message=detail_msg,
                        details={"constraint": "unique_violation"},
                        endpoint=request.url.path,
                        method=request.method,
                        request_id=request_id,
                    ),
                    headers={"X-Request-ID": request_id},
                )
            if "foreign key" in err_msg or "foreignkey" in err_msg or "foreign key" in orig_lower:
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=error_envelope(
                        code="DATABASE_CONSTRAINT_FAILED",
                        category=ErrorCategory.DATABASE,
                        layer=ErrorLayer.DATABASE,
                        message="Referenced record does not exist or is constrained by existing relationships.",
                        details={"constraint": "foreign_key_violation"},
                        endpoint=request.url.path,
                        method=request.method,
                        request_id=request_id,
                    ),
                    headers={"X-Request-ID": request_id},
                )
            if "check" in err_msg or "check constraint" in orig_lower:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content=error_envelope(
                        code="VALIDATION_ERROR",
                        category=ErrorCategory.VALIDATION,
                        layer=ErrorLayer.DATABASE,
                        message="Value violates database check constraint.",
                        details={"constraint": "check_violation"},
                        endpoint=request.url.path,
                        method=request.method,
                        request_id=request_id,
                    ),
                    headers={"X-Request-ID": request_id},
                )
            if "not-null" in err_msg or "null value in column" in orig_lower:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content=error_envelope(
                        code="VALIDATION_ERROR",
                        category=ErrorCategory.VALIDATION,
                        layer=ErrorLayer.DATABASE,
                        message="Required database column value cannot be null.",
                        details={"constraint": "not_null_violation"},
                        endpoint=request.url.path,
                        method=request.method,
                        request_id=request_id,
                    ),
                    headers={"X-Request-ID": request_id},
                )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=error_envelope(
                    code="CONFLICT",
                    category=ErrorCategory.DATABASE,
                    layer=ErrorLayer.DATABASE,
                    message="Database integrity constraint violated.",
                    endpoint=request.url.path,
                    method=request.method,
                    request_id=request_id,
                ),
                headers={"X-Request-ID": request_id},
            )

        # 4. Data format / length errors
        if isinstance(exc, DataError) or "dataerror" in err_msg:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content=error_envelope(
                    code="VALIDATION_ERROR",
                    category=ErrorCategory.VALIDATION,
                    layer=ErrorLayer.DATABASE,
                    message="Invalid data format or value length exceeds maximum allowed limit.",
                    endpoint=request.url.path,
                    method=request.method,
                    request_id=request_id,
                ),
                headers={"X-Request-ID": request_id},
            )

        # 5. General Database Query Failure
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(
                code="DATABASE_QUERY_FAILED",
                category=ErrorCategory.DATABASE,
                layer=ErrorLayer.DATABASE,
                message="A database query execution error occurred while processing this request.",
                details="The database operation could not be completed.",
                endpoint=request.url.path,
                method=request.method,
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _get_request_id(request)
        exc_type = type(exc).__name__
        logger.error(
            "unhandled_server_exception",
            path=request.url.path,
            method=request.method,
            exception_type=exc_type,
            request_id=request_id,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(
                code="INTERNAL_SERVER_ERROR",
                category=ErrorCategory.SYSTEM,
                layer=ErrorLayer.SYSTEM,
                message="An unexpected internal server error occurred while processing this request.",
                details=f"Unexpected {exc_type} during request execution. Traceable via requestId: {request_id}",
                endpoint=request.url.path,
                method=request.method,
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id},
        )
