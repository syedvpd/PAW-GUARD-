"""Application exception hierarchy and FastAPI exception handlers.

Never leak SQL errors, stack traces, or framework internals to clients — every AppException
carries a stable machine-readable `code` and a safe client-facing `message`.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from pawguard.core.logging import get_logger
from pawguard.core.responses import error_envelope

logger = get_logger(__name__)


class AppException(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "APP_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        self.message = message
        self.code = code or self.code
        self.details = details
        super().__init__(message)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class ValidationFailedError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_FAILED"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class TooManyRequestsError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "TOO_MANY_REQUESTS"


def parse_enum[EnumT: StrEnum](
    enum_cls: type[EnumT], value: str, *, field_name: str = "status"
) -> EnumT:
    """Converts a raw string into a StrEnum member, raising a clean 422
    instead of letting the constructor's bare ValueError fall through to
    the generic 500 handler.

    Bulk-status-update endpoints across most modules call e.g.
    RescueStatus(payload.status) directly on a freeform BulkStatusUpdateRequest
    string field - any value that isn't a real enum member (a typo, or a
    status valid for a different module) crashed with an unhandled 500
    instead of a validation error. Use this wherever a raw string from a
    request needs to become a StrEnum.
    """
    try:
        return enum_cls(value)
    except ValueError as exc:
        valid = ", ".join(m.value for m in enum_cls)
        raise ValidationFailedError(
            f"Invalid {field_name} '{value}'. Must be one of: {valid}."
        ) from exc


def _sanitize_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Ensure all error detail values are JSON-serializable.

    Pydantic's ``exc.errors()`` may include non-serializable objects such
    as ``ValueError`` instances inside ``ctx.error``.
    """
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


def clean_error_message(msg: str) -> str:
    """Format validation and exception messages to be concise, clean (1-2 lines),
    and production-ready per enterprise API design standards (Google / Amazon).

    Strips raw internal stack traces, MissingGreenlet/SQLAlchemy framework errors,
    Pydantic documentation URLs, and verbose dump blocks.
    """
    if not msg:
        return "Invalid request payload or schema validation error."

    if "MissingGreenlet" in msg or "Error extracting attribute" in msg or "get_attribute_error" in msg:
        return "Internal processing error: database entity relations failed to load during serialization."

    import re
    msg = re.sub(r"\s*For further information visit https://errors\.pydantic\.dev/[^\s]+", "", msg)
    msg = re.sub(r"\s*\[type=[^\]]+\]", "", msg)
    msg = re.sub(r"\(Background on this error at: [^\)]+\)", "", msg)

    lines = [line.strip() for line in msg.splitlines() if line.strip()]
    if not lines:
        return "Request validation failed."

    if len(lines) == 1:
        return lines[0]

    # Summarize Pydantic multi-line errors into a clean 1-line statement
    cleaned_lines = []
    for line in lines:
        if line.startswith("1 validation error for") or line.startswith("Validation error for"):
            continue
        cleaned_lines.append(line)

    return " | ".join(cleaned_lines) if cleaned_lines else lines[0]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.info(
            "app_exception",
            code=exc.code,
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(code=exc.code, message=clean_error_message(exc.message), details=exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Build concise 1-line error message for frontend readability
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

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_envelope(
                code="VALIDATION_FAILED",
                message=clean_error_message(first_msg),
                details=err_details,
            ),
        )

    from fastapi.exceptions import ResponseValidationError

    @app.exception_handler(ResponseValidationError)
    async def response_validation_exception_handler(
        request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        logger.error(
            "response_validation_error",
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(
                code="RESPONSE_SERIALIZATION_FAILED",
                message="An internal error occurred while formatting response data.",
            ),
        )

    @app.exception_handler(ValueError)
    async def value_exception_handler(request: Request, exc: ValueError) -> JSONResponse:
        logger.info(
            "value_error",
            path=request.url.path,
            message=str(exc),
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_envelope(
                code="VALIDATION_FAILED",
                message=clean_error_message(str(exc)) or "Invalid value provided.",
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(code="HTTP_ERROR", message=str(exc.detail)),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        from sqlalchemy.exc import DataError, IntegrityError

        err_msg = str(exc).lower()
        orig_msg = str(getattr(exc, "orig", ""))

        logger.error(
            "database_error",
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
            exc_info=exc,
        )

        if isinstance(exc, IntegrityError) or "integrityerror" in err_msg:
            if "unique" in err_msg or "unique" in orig_msg.lower() or "duplicate key" in err_msg:
                # Extract specific field/table information if possible
                detail_msg = "A record with this unique identifier or key already exists."
                if "Key (" in orig_msg:
                    # e.g. Key (email)=(test@example.com) already exists.
                    key_part = orig_msg.split("Key (")[-1].split(")")[0] if "Key (" in orig_msg else ""
                    if key_part:
                        detail_msg = f"A record with {key_part} already exists."
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=error_envelope(
                        code="CONFLICT",
                        message=detail_msg,
                        details={"constraint": "unique_violation"},
                    ),
                )
            elif "foreign key" in err_msg or "foreignkey" in err_msg or "foreign key" in orig_msg.lower():
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=error_envelope(
                        code="INVALID_REFERENCE",
                        message="Referenced record does not exist or cannot be modified due to existing references.",
                        details={"constraint": "foreign_key_violation"},
                    ),
                )
            elif "check" in err_msg or "check constraint" in orig_msg.lower():
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content=error_envelope(
                        code="VALIDATION_FAILED",
                        message="Value violates database check constraint.",
                        details={"constraint": "check_violation"},
                    ),
                )
            else:
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=error_envelope(
                        code="CONFLICT",
                        message="Database integrity constraint violated.",
                    ),
                )

        if isinstance(exc, DataError) or "dataerror" in err_msg:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content=error_envelope(
                    code="VALIDATION_FAILED",
                    message="Invalid data format or value length exceeds maximum allowed limit.",
                ),
            )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(code="INTERNAL_ERROR", message="An internal database error occurred."),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(code="INTERNAL_ERROR", message="An unexpected internal server error occurred."),
        )
