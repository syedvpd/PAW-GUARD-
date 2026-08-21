"""API router for Push Notification Governance & Admin Approval Control Engine."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.notifications.governance_schemas import (
    ApprovalActionRequest,
    ApprovalQueueItemResponse,
    GlobalConfigResponse,
    GlobalConfigUpdate,
    GovernanceAuditLogResponse,
    ModuleConfigResponse,
    ModuleConfigUpdate,
    NotificationOverviewResponse,
    TriggerConfigResponse,
    TriggerConfigUpdate,
)
from pawguard.modules.notifications.governance_service import NotificationGovernanceService
from pawguard.modules.notifications.models import (
    NotificationApprovalQueue,
    NotificationGlobalConfig,
    NotificationGovernanceAuditLog,
    NotificationModuleConfig,
    NotificationTriggerConfig,
)

admin_router = APIRouter(prefix="/admin/notifications", tags=["admin-notifications"])


def get_gov_service(db: AsyncSession = Depends(get_db)) -> NotificationGovernanceService:
    return NotificationGovernanceService(db)


# ── System Dashboard Overview ────────────────────────────────────────────────


@admin_router.get(
    "/overview",
    response_model=ApiResponse[NotificationOverviewResponse],
    dependencies=[Depends(require_permission("notification:view", "system:admin"))],
)
async def get_notifications_overview(
    db: AsyncSession = Depends(get_db),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[NotificationOverviewResponse]:
    await service.ensure_seed_defaults()
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # Counts from approval queue & dispatch history
    total_today = (
        await db.execute(
            select(func.count(NotificationApprovalQueue.id)).where(
                NotificationApprovalQueue.created_at >= today_start
            )
        )
    ).scalar() or 0

    pending = (
        await db.execute(
            select(func.count(NotificationApprovalQueue.id)).where(
                NotificationApprovalQueue.status == "PENDING_APPROVAL"
            )
        )
    ).scalar() or 0

    sent = (
        await db.execute(
            select(func.count(NotificationApprovalQueue.id)).where(
                NotificationApprovalQueue.status == "SENT",
                NotificationApprovalQueue.updated_at >= today_start,
            )
        )
    ).scalar() or 0

    failed = (
        await db.execute(
            select(func.count(NotificationApprovalQueue.id)).where(
                NotificationApprovalQueue.status == "FAILED",
                NotificationApprovalQueue.updated_at >= today_start,
            )
        )
    ).scalar() or 0

    blocked = (
        await db.execute(
            select(func.count(NotificationApprovalQueue.id)).where(
                NotificationApprovalQueue.status == "BLOCKED",
                NotificationApprovalQueue.created_at >= today_start,
            )
        )
    ).scalar() or 0

    paused = (
        await db.execute(
            select(func.count(NotificationApprovalQueue.id)).where(
                NotificationApprovalQueue.status == "PAUSED"
            )
        )
    ).scalar() or 0

    rejected = (
        await db.execute(
            select(func.count(NotificationApprovalQueue.id)).where(
                NotificationApprovalQueue.status == "REJECTED",
                NotificationApprovalQueue.updated_at >= today_start,
            )
        )
    ).scalar() or 0

    global_cfg = (await db.execute(select(NotificationGlobalConfig))).scalars().first()
    g_status = global_cfg.push_status if global_cfg else "ENABLED"
    g_reason = global_cfg.reason if global_cfg else None

    return ApiResponse(
        data=NotificationOverviewResponse(
            total_today=total_today,
            pending_approval=pending,
            sent_today=sent,
            failed_today=failed,
            blocked_today=blocked,
            paused_today=paused,
            rejected_today=rejected,
            global_push_status=g_status,
            global_pause_reason=g_reason,
        )
    )


# ── Global Controls (Level 1) ────────────────────────────────────────────────


@admin_router.get(
    "/global",
    response_model=ApiResponse[GlobalConfigResponse],
    dependencies=[Depends(require_permission("notification:view", "system:admin"))],
)
async def get_global_config(
    db: AsyncSession = Depends(get_db),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[GlobalConfigResponse]:
    await service.ensure_seed_defaults()
    cfg = (await db.execute(select(NotificationGlobalConfig))).scalars().first()
    return ApiResponse(data=GlobalConfigResponse.model_validate(cfg))


@admin_router.put(
    "/global",
    response_model=ApiResponse[GlobalConfigResponse],
    dependencies=[Depends(require_permission("notification:global_control", "system:admin"))],
)
async def update_global_config(
    payload: GlobalConfigUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[GlobalConfigResponse]:
    if payload.push_status not in ("ENABLED", "DISABLED", "PAUSED"):
        raise ValidationFailedError("push_status must be 'ENABLED', 'DISABLED', or 'PAUSED'.")

    await service.ensure_seed_defaults()
    cfg = (await db.execute(select(NotificationGlobalConfig))).scalars().first()
    assert cfg is not None
    old_status = cfg.push_status
    cfg.push_status = payload.push_status
    cfg.reason = payload.reason
    cfg.updated_by = current_user.id
    await db.flush()

    await service.record_audit(
        trigger_code="global_control",
        module_name="system",
        actor_user_id=current_user.id,
        action=f"GLOBAL_{payload.push_status}",
        previous_status=old_status,
        new_status=payload.push_status,
        reason=payload.reason,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=GlobalConfigResponse.model_validate(cfg),
        message="Global push notification settings updated.",
    )


# ── Module Controls (Level 2) ────────────────────────────────────────────────


@admin_router.get(
    "/modules",
    response_model=ApiResponse[list[ModuleConfigResponse]],
    dependencies=[Depends(require_permission("notification:view", "system:admin"))],
)
async def list_module_configs(
    db: AsyncSession = Depends(get_db),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[list[ModuleConfigResponse]]:
    await service.ensure_seed_defaults()
    modules = (
        (
            await db.execute(
                select(NotificationModuleConfig).order_by(NotificationModuleConfig.module_name)
            )
        )
        .scalars()
        .all()
    )
    return ApiResponse(data=[ModuleConfigResponse.model_validate(m) for m in modules])


@admin_router.put(
    "/modules/{module_name}",
    response_model=ApiResponse[ModuleConfigResponse],
    dependencies=[Depends(require_permission("notification:manage", "system:admin"))],
)
async def update_module_config(
    module_name: str,
    payload: ModuleConfigUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[ModuleConfigResponse]:
    if payload.push_status not in ("ENABLED", "DISABLED", "PAUSED"):
        raise ValidationFailedError("push_status must be 'ENABLED', 'DISABLED', or 'PAUSED'.")

    await service.ensure_seed_defaults()
    stmt = select(NotificationModuleConfig).where(
        NotificationModuleConfig.module_name == module_name
    )
    mod = (await db.execute(stmt)).scalars().first()
    if mod is None:
        raise NotFoundError(f"Module config '{module_name}' not found.")

    old_status = mod.push_status
    mod.push_status = payload.push_status
    mod.reason = payload.reason
    mod.updated_by = current_user.id
    await db.flush()

    await service.record_audit(
        trigger_code=f"{module_name}_control",
        module_name=module_name,
        actor_user_id=current_user.id,
        action=f"MODULE_{payload.push_status}",
        previous_status=old_status,
        new_status=payload.push_status,
        reason=payload.reason,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ModuleConfigResponse.model_validate(mod),
        message=f"Module '{module_name}' settings updated.",
    )


# ── Trigger Controls (Level 3) ────────────────────────────────────────────────


@admin_router.get(
    "/triggers",
    response_model=ApiResponse[list[TriggerConfigResponse]],
    dependencies=[Depends(require_permission("notification:view", "system:admin"))],
)
async def list_trigger_configs(
    module_name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[list[TriggerConfigResponse]]:
    await service.ensure_seed_defaults()
    stmt = select(NotificationTriggerConfig)
    if module_name:
        stmt = stmt.where(NotificationTriggerConfig.module_name == module_name)
    stmt = stmt.order_by(
        NotificationTriggerConfig.module_name, NotificationTriggerConfig.trigger_code
    )
    triggers = (await db.execute(stmt)).scalars().all()
    return ApiResponse(data=[TriggerConfigResponse.model_validate(t) for t in triggers])


@admin_router.put(
    "/triggers/{trigger_id}",
    response_model=ApiResponse[TriggerConfigResponse],
    dependencies=[Depends(require_permission("notification:manage", "system:admin"))],
)
async def update_trigger_config(
    trigger_id: uuid.UUID,
    payload: TriggerConfigUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[TriggerConfigResponse]:
    stmt = select(NotificationTriggerConfig).where(NotificationTriggerConfig.id == trigger_id)
    trig = (await db.execute(stmt)).scalars().first()
    if trig is None:
        raise NotFoundError("Trigger config not found.")

    old_status = trig.push_status
    if payload.push_status is not None:
        if payload.push_status not in ("ENABLED", "DISABLED", "PAUSED"):
            raise ValidationFailedError("push_status must be 'ENABLED', 'DISABLED', or 'PAUSED'.")
        trig.push_status = payload.push_status
    if payload.email_enabled is not None:
        trig.email_enabled = payload.email_enabled
    if payload.requires_approval is not None:
        trig.requires_approval = payload.requires_approval
    if payload.default_priority is not None:
        trig.default_priority = payload.default_priority

    trig.updated_by = current_user.id
    await db.flush()

    await service.record_audit(
        trigger_code=trig.trigger_code,
        module_name=trig.module_name,
        actor_user_id=current_user.id,
        action="TRIGGER_UPDATED",
        previous_status=old_status,
        new_status=trig.push_status,
        reason=f"Updated settings for trigger '{trig.trigger_code}'",
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=TriggerConfigResponse.model_validate(trig),
        message=f"Trigger '{trig.trigger_code}' configuration updated.",
    )


# ── Admin Approval Queue Workflows ───────────────────────────────────────────


@admin_router.get(
    "/approvals",
    response_model=ApiResponse[list[ApprovalQueueItemResponse]],
    dependencies=[Depends(require_permission("notification:view", "system:admin"))],
)
async def list_approval_queue(
    status: str | None = Query("PENDING_APPROVAL"),
    module_name: str | None = Query(None),
    priority: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ApprovalQueueItemResponse]]:
    stmt = select(NotificationApprovalQueue)
    if status:
        stmt = stmt.where(NotificationApprovalQueue.status == status)
    if module_name:
        stmt = stmt.where(NotificationApprovalQueue.module_name == module_name)
    if priority:
        stmt = stmt.where(NotificationApprovalQueue.priority == priority)

    stmt = stmt.order_by(NotificationApprovalQueue.created_at.desc())
    items = (await db.execute(stmt)).scalars().all()
    return ApiResponse(data=[ApprovalQueueItemResponse.model_validate(item) for item in items])


@admin_router.get(
    "/approvals/{queue_id}",
    response_model=ApiResponse[ApprovalQueueItemResponse],
    dependencies=[Depends(require_permission("notification:view", "system:admin"))],
)
async def get_approval_item(
    queue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ApprovalQueueItemResponse]:
    stmt = select(NotificationApprovalQueue).where(NotificationApprovalQueue.id == queue_id)
    item = (await db.execute(stmt)).scalars().first()
    if item is None:
        raise NotFoundError("Approval queue item not found.")
    return ApiResponse(data=ApprovalQueueItemResponse.model_validate(item))


@admin_router.post(
    "/approvals/{queue_id}/approve",
    response_model=ApiResponse[ApprovalQueueItemResponse],
    dependencies=[Depends(require_permission("notification:approve", "system:admin"))],
)
async def approve_notification(
    queue_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[ApprovalQueueItemResponse]:
    item = await service.approve_notification(
        queue_id=queue_id,
        actor_user_id=current_user.id,
        actor_role="admin",
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ApprovalQueueItemResponse.model_validate(item),
        message="Notification approved and queued for FCM dispatch.",
    )


@admin_router.post(
    "/approvals/{queue_id}/reject",
    response_model=ApiResponse[ApprovalQueueItemResponse],
    dependencies=[Depends(require_permission("notification:reject", "system:admin"))],
)
async def reject_notification(
    queue_id: uuid.UUID,
    payload: ApprovalActionRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[ApprovalQueueItemResponse]:
    item = await service.reject_notification(
        queue_id=queue_id,
        actor_user_id=current_user.id,
        reason=payload.reason,
        actor_role="admin",
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ApprovalQueueItemResponse.model_validate(item), message="Notification rejected."
    )


@admin_router.post(
    "/approvals/{queue_id}/pause",
    response_model=ApiResponse[ApprovalQueueItemResponse],
    dependencies=[Depends(require_permission("notification:pause", "system:admin"))],
)
async def pause_notification(
    queue_id: uuid.UUID,
    payload: ApprovalActionRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[ApprovalQueueItemResponse]:
    item = await service.pause_notification(
        queue_id=queue_id,
        actor_user_id=current_user.id,
        reason=payload.reason,
        actor_role="admin",
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ApprovalQueueItemResponse.model_validate(item), message="Notification paused."
    )


@admin_router.post(
    "/approvals/{queue_id}/resume",
    response_model=ApiResponse[ApprovalQueueItemResponse],
    dependencies=[Depends(require_permission("notification:resume", "system:admin"))],
)
async def resume_notification(
    queue_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationGovernanceService = Depends(get_gov_service),
) -> ApiResponse[ApprovalQueueItemResponse]:
    item = await service.resume_notification(
        queue_id=queue_id,
        actor_user_id=current_user.id,
        actor_role="admin",
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ApprovalQueueItemResponse.model_validate(item), message="Notification resumed."
    )


# ── Dispatch Logs & Governance Audit Logs ────────────────────────────────────


@admin_router.get(
    "/dispatch-logs",
    response_model=ApiResponse[list[ApprovalQueueItemResponse]],
    dependencies=[Depends(require_permission("notification:view", "system:admin"))],
)
async def list_dispatch_logs(
    module_name: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ApprovalQueueItemResponse]]:
    stmt = select(NotificationApprovalQueue)
    if module_name:
        stmt = stmt.where(NotificationApprovalQueue.module_name == module_name)
    if status:
        stmt = stmt.where(NotificationApprovalQueue.status == status)

    stmt = stmt.order_by(NotificationApprovalQueue.created_at.desc()).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    return ApiResponse(data=[ApprovalQueueItemResponse.model_validate(i) for i in items])


@admin_router.get(
    "/audit-logs",
    response_model=ApiResponse[list[GovernanceAuditLogResponse]],
    dependencies=[Depends(require_permission("notification:audit", "system:admin"))],
)
async def list_governance_audit_logs(
    module_name: str | None = Query(None),
    trigger_code: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[GovernanceAuditLogResponse]]:
    stmt = select(NotificationGovernanceAuditLog)
    if module_name:
        stmt = stmt.where(NotificationGovernanceAuditLog.module_name == module_name)
    if trigger_code:
        stmt = stmt.where(NotificationGovernanceAuditLog.trigger_code == trigger_code)
    if action:
        stmt = stmt.where(NotificationGovernanceAuditLog.action == action)

    stmt = stmt.order_by(NotificationGovernanceAuditLog.created_at.desc()).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()
    return ApiResponse(
        data=[GovernanceAuditLogResponse.model_validate(log_entry) for log_entry in logs]
    )
