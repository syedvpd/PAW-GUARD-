"""Admin audit log viewer endpoints (RULE-004)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.auth.repository import AuthAuditLogRepository

audit_router = APIRouter(prefix="/admin/audit-logs", tags=["admin-audit"])


@audit_router.get(
    "",
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict[str, Any]]]:
    repo = AuthAuditLogRepository(db)
    entries = await repo.list(skip=skip, limit=limit, event_type=event_type, user_id=user_id)
    return ApiResponse(
        data=[
            {
                "id": str(e.id),
                "user_id": str(e.user_id) if e.user_id else None,
                "event_type": e.event_type,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "event_metadata": e.event_metadata,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]
    )


@audit_router.get(
    "/export",
    dependencies=[Depends(require_permission("system:admin"))],
)
@audit_router.post(
    "/export",
    dependencies=[Depends(require_permission("system:admin"))],
)
async def export_audit_logs(
    format: str = Query("csv", description="Export format: 'csv' or 'json'"),
    event_type: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    repo = AuthAuditLogRepository(db)
    entries = await repo.list(skip=0, limit=1000, event_type=event_type, user_id=user_id)

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "user_id", "event_type", "ip_address", "user_agent", "created_at"])
        for e in entries:
            writer.writerow([
                str(e.id),
                str(e.user_id) if e.user_id else "",
                e.event_type,
                e.ip_address or "",
                e.user_agent or "",
                e.created_at.isoformat() if e.created_at else "",
            ])
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )

    return ApiResponse(
        data=[
            {
                "id": str(e.id),
                "user_id": str(e.user_id) if e.user_id else None,
                "event_type": e.event_type,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "event_metadata": e.event_metadata,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
        message="Audit logs exported successfully.",
    )


@audit_router.get(
    "/{entry_id}",
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_audit_log(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, Any]]:
    repo = AuthAuditLogRepository(db)
    entry = await repo.get_by_id(entry_id)
    if entry is None:
        from pawguard.core.exceptions import NotFoundError
        raise NotFoundError("Audit log entry not found.")
    return ApiResponse(
        data={
            "id": str(entry.id),
            "user_id": str(entry.user_id) if entry.user_id else None,
            "event_type": entry.event_type,
            "ip_address": entry.ip_address,
            "user_agent": entry.user_agent,
            "event_metadata": entry.event_metadata,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
    )
