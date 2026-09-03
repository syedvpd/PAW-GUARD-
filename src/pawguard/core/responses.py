"""Standard API response envelope used by every endpoint."""

from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

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


class ErrorDetail(BaseModel):
    code: str = Field(..., examples=["RESOURCE_NOT_FOUND"])
    category: str = Field(..., examples=["RESOURCE"])
    layer: str = Field(..., examples=["SERVICE"])
    message: str = Field(..., examples=["The requested entity was not found."])
    details: Any = Field(None, examples=[{"field": "id"}])
    endpoint: str | None = Field(None, examples=["/api/v1/dogs"])
    method: str | None = Field(None, examples=["GET"])
    requestId: str | None = Field(None, alias="requestId", examples=["req_92ab31c5"])
    timestamp: str = Field(..., examples=["2026-09-03T09:20:00.000Z"])

    model_config = ConfigDict(populate_by_name=True)


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


def error_envelope(
    *,
    code: str,
    message: str,
    category: str = "SYSTEM",
    layer: str = "SYSTEM",
    details: Any = None,
    endpoint: str | None = None,
    method: str | None = None,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()
    return {
        "success": False,
        "error": {
            "code": code,
            "category": category,
            "layer": layer,
            "message": message,
            "details": details,
            "endpoint": endpoint,
            "method": method,
            "requestId": request_id,
            "request_id": request_id,
            "timestamp": timestamp,
        },
    }
