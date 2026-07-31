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
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
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
            content=error_envelope(code=exc.code, message=exc.message, details=exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_envelope(
                code="VALIDATION_FAILED",
                message="Request validation failed.",
                details=_sanitize_errors(exc.errors()),
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
        logger.error(
            "unhandled_database_error",
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(code="INTERNAL_ERROR", message="An internal error occurred."),
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
            content=error_envelope(code="INTERNAL_ERROR", message="An internal error occurred."),
        )
