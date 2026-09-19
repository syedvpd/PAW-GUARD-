"""Admin audit log viewer endpoints (RULE-004)."""

import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.cache_decorator import cache_response
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.rbac import require_admin_tier
from pawguard.modules.auth.repository import AuthAuditLogRepository, audit_filters

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
    dependencies=[Depends(require_admin_tier())],
)
@cache_response(ttl_seconds=30, namespace="admin")
async def list_audit_logs(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    module: str | None = Query(None, max_length=40),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict[str, Any]]]:
    repo = AuthAuditLogRepository(db)
    entries = await repo.list(
        skip=skip,
        limit=limit,
        event_type=event_type,
        user_id=user_id,
        module=module,
        date_from=date_from,
        date_to=date_to,
    )
    return ApiResponse(data=[_format_audit_entry(e) for e in entries])


@audit_router.get(
    "/export",
    dependencies=[Depends(require_admin_tier())],
)
@audit_router.post(
    "/export",
    dependencies=[Depends(require_admin_tier())],
)
async def export_audit_logs(
    format: str = Query("csv", description="Export format: 'csv' or 'json'"),
    event_type: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    module: str | None = Query(None, max_length=40),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    import csv
    import io

    from fastapi.responses import Response
    from sqlalchemy import select

    from pawguard.modules.auth.models import AuthAuditLog, User

    stmt = select(
        AuthAuditLog.id,
        AuthAuditLog.user_id,
        User.email.label("user_name"),
        User.full_name,
        AuthAuditLog.event_type,
        AuthAuditLog.ip_address,
        AuthAuditLog.user_agent,
        AuthAuditLog.event_metadata,
        AuthAuditLog.before_state,
        AuthAuditLog.after_state,
        AuthAuditLog.created_at,
    ).outerjoin(User, User.id == AuthAuditLog.user_id)

    for condition in audit_filters(
        event_type=event_type,
        user_id=user_id,
        module=module,
        date_from=date_from,
        date_to=date_to,
    ):
        stmt = stmt.where(condition)
    stmt = stmt.order_by(AuthAuditLog.created_at.desc()).limit(limit)

    rows = (await db.execute(stmt)).all()

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "user_id",
                "user_name",
                "full_name",
                "status",
                "event_type",
                "ip_address",
                "user_agent",
                "before_state",
                "after_state",
                "created_at",
            ]
        )
        for r in rows:
            meta = r.event_metadata or {}
            if "status" in meta:
                status_val = str(meta["status"]).lower()
            elif any(
                term in r.event_type for term in ["_failed", "_rejected", "_denied", "_error"]
            ):
                status_val = "failed"
            else:
                status_val = "success"

            writer.writerow(
                [
                    str(r.id),
                    str(r.user_id) if r.user_id else "",
                    r.user_name or "",
                    r.full_name or "",
                    status_val,
                    r.event_type,
                    r.ip_address or "",
                    r.user_agent or "",
                    json.dumps(r.before_state) if r.before_state is not None else "",
                    json.dumps(r.after_state) if r.after_state is not None else "",
                    r.created_at.isoformat() if r.created_at else "",
                ]
            )
        csv_bytes = output.getvalue().encode("utf-8")
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )

    data = []
    for r in rows:
        meta = r.event_metadata or {}
        if "status" in meta:
            status_val = str(meta["status"]).lower()
        elif any(term in r.event_type for term in ["_failed", "_rejected", "_denied", "_error"]):
            status_val = "failed"
        else:
            status_val = "success"
        data.append(
            {
                "id": str(r.id),
                "user_id": str(r.user_id) if r.user_id else None,
                "user_name": r.user_name,
                "username": r.user_name,
                "email": r.user_name,
                "full_name": r.full_name,
                "status": status_val,
                "event_type": r.event_type,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
                "event_metadata": r.event_metadata,
                "before_state": r.before_state,
                "after_state": r.after_state,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return ApiResponse(
        data=data,
        message="Audit logs exported successfully.",
    )


@audit_router.get(
    "/{entry_id}",
    dependencies=[Depends(require_admin_tier())],
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
