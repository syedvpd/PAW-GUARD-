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


def _format_audit_entry(e: Any) -> dict[str, Any]:
    user = getattr(e, "user", None)
    email = user.email if user else None
    full_name = user.full_name if user else None
    roles = [r.name for r in user.roles] if user and hasattr(user, "roles") and user.roles else []
    primary_role = roles[0] if roles else ("user" if user else "system")

    meta = e.event_metadata or {}
    if "status" in meta:
        status_val = str(meta["status"]).lower()
    elif any(term in e.event_type for term in ["_failed", "_rejected", "_denied", "_error"]):
        status_val = "failed"
    else:
        status_val = "success"

    return {
        "id": str(e.id),
        "user_id": str(e.user_id) if e.user_id else None,
        "user_name": email,
        "username": email,
        "email": email,
        "full_name": full_name,
        "role": primary_role,
        "roles": roles,
        "status": status_val,
        "event_type": e.event_type,
        "ip_address": e.ip_address,
        "user_agent": e.user_agent,
        "event_metadata": e.event_metadata,
        "before_state": getattr(e, "before_state", None),
        "after_state": getattr(e, "after_state", None),
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


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
    return ApiResponse(data=[_format_audit_entry(e) for e in entries])


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
        writer.writerow([
            "id", "user_id", "user_name", "full_name", "role", "status",
            "event_type", "ip_address", "user_agent", "created_at"
        ])
        for e in entries:
            formatted = _format_audit_entry(e)
            writer.writerow([
                formatted["id"],
                formatted["user_id"] or "",
                formatted["user_name"] or "",
                formatted["full_name"] or "",
                formatted["role"] or "",
                formatted["status"],
                formatted["event_type"],
                formatted["ip_address"] or "",
                formatted["user_agent"] or "",
                formatted["created_at"] or "",
            ])
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )

    return ApiResponse(
        data=[_format_audit_entry(e) for e in entries],
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
    return ApiResponse(data=_format_audit_entry(entry))
