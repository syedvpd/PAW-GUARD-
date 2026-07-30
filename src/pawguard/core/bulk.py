"""Bulk operation schemas and utilities shared by all modules.

Provides standard request/response models for bulk status updates,
bulk soft-delete, and bulk attribute updates.
"""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BulkIdsRequest(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ids": [
                    "550e8400-e29b-41d4-a716-446655440000",
                    "550e8400-e29b-41d4-a716-446655440001",
                ]
            }
        }
    )


class BulkStatusUpdateRequest(BulkIdsRequest):
    status: str = Field(..., min_length=1, max_length=64)


class BulkDeleteRequest(BulkIdsRequest):
    pass


class BulkOperationResult(BaseModel):
    processed: int
    failed: int
    errors: list[dict[str, Any]] = []


class BulkDeleteResponse(BaseModel):
    success: bool = True
    message: str
    deleted_count: int


class BulkStatusUpdateResponse(BaseModel):
    success: bool = True
    message: str
    updated_count: int
