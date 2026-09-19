"""Super Administrator data backups (PRR 2.1). History lives in the audit log."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.rate_limiter import rate_limit, resolve_client_ip
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.admin.backup import build_backup
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import AuthAuditEventType, AuthAuditLog
from pawguard.modules.auth.rbac import require_role
from pawguard.services.audit_service import AuditService

backup_router = APIRouter(prefix="/admin/backups", tags=["admin-backups"])


def _history_entry(e: AuthAuditLog) -> dict[str, Any]:
    meta = e.event_metadata or {}
    return {
        "id": str(e.id),
        "key": meta.get("filename", ""),
        "file_name": meta.get("filename", ""),
        "size_bytes": meta.get("size_bytes", 0),
        "table_count": meta.get("table_count", 0),
        "row_count": meta.get("row_count", 0),
        "created_by": e.user.email if e.user else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@backup_router.get("", dependencies=[Depends(require_role("super_admin"))])
async def list_backups(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict[str, Any]]]:
    stmt = (
        select(AuthAuditLog)
        .options(selectinload(AuthAuditLog.user))
        .where(AuthAuditLog.event_type == AuthAuditEventType.BACKUP_CREATED.value)
        .order_by(AuthAuditLog.created_at.desc())
        .limit(limit)
    )
    entries = (await db.execute(stmt)).scalars().all()
    return ApiResponse(data=[_history_entry(e) for e in entries])


@backup_router.post(
    "",
    dependencies=[
        Depends(require_role("super_admin")),
        Depends(rate_limit("admin_backup", 5, 3600)),
    ],
)
async def create_backup(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    payload, counts = await build_backup(db)
    filename = f"pawguard-backup-{datetime.now(UTC):%Y%m%d-%H%M%S}.json.gz"
    await AuditService(db).record(
        event_type=AuthAuditEventType.BACKUP_CREATED,
        actor_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={
            "filename": filename,
            "size_bytes": len(payload),
            "table_count": len(counts),
            "row_count": sum(counts.values()),
        },
    )
    await db.commit()
    return Response(
        content=payload,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
