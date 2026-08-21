"""Standard API response envelope used by every endpoint."""

from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse[T](BaseModel):
    success: bool = True
    data: T | None = None
    message: str | None = None


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedResponse[T](BaseModel):
    success: bool = True
    data: list[T]
    meta: PaginationMeta


def error_envelope(*, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }
