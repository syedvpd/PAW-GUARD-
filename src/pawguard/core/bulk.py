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
    status: str = Field(..., min_length=1, max_length=64, examples=["active"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ids": [
                    "550e8400-e29b-41d4-a716-446655440000",
                    "550e8400-e29b-41d4-a716-446655440001",
                ],
                "status": "active",
            }
        }
    )


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


async def bulk_set_column(
    session: Any,
    model: type[Any],
    ids: list[uuid.UUID] | tuple[uuid.UUID, ...],
    **values: Any,
) -> int:
    """Executes a parameterized bulk UPDATE query setting columns across specified IDs."""
    if not ids:
        return 0
    from sqlalchemy import update

    stmt = (
        update(model)
        .where(model.id.in_(list(ids)))
        .values(**values)
        .execution_options(synchronize_session="fetch")
    )
    result = await session.execute(stmt)
    await session.flush()
    return int(result.rowcount or 0)


class BulkOperationMixin:
    """Reusable mixin providing standard bulk operation workflows with hooks."""

    async def bulk_update_status(
        self,
        session: Any,
        model: type[Any],
        ids: list[uuid.UUID] | tuple[uuid.UUID, ...],
        new_status: str,
        status_column: str = "status",
        before_hook: Any = None,
        after_hook: Any = None,
    ) -> int:
        if before_hook:
            await before_hook(ids, new_status)
        count = await bulk_set_column(session, model, ids, **{status_column: new_status})
        if after_hook:
            await after_hook(ids, new_status)
        return count
