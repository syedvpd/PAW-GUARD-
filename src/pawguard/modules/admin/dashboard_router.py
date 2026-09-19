"""Admin dashboard endpoints: analytics, metrics, system overview (RULE-004)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.cache_decorator import cache_response
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.admin.dashboard_repository import DashboardRepository
from pawguard.modules.admin.dashboard_service import DashboardService
from pawguard.modules.auth.models import AuthAuditEventType, AuthAuditLog, Role, User, UserRole
from pawguard.modules.auth.rbac import require_permission, require_role
from pawguard.redis.client import RedisClient, get_redis

admin_dashboard_router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


def get_dashboard_service(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> DashboardService:
    repo = DashboardRepository(db)
    return DashboardService(repo, redis=redis)


@admin_dashboard_router.get(
    "/metrics",
    response_model=ApiResponse[dict[str, int]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_system_metrics(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, int]]:
    metrics = await service.get_system_metrics()
    return ApiResponse(data=metrics)


@admin_dashboard_router.get(
    "/summary",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_summary(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_summary()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/kpis",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_kpis(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_kpis()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/charts",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_charts(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_charts()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/recent-activity",
    response_model=ApiResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_recent_activity(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[list[dict[str, Any]]]:
    data = await service.get_recent_activity(limit=limit)
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/inventory-alerts",
    response_model=ApiResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("system:admin", "inventory:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_inventory_alerts(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[list[dict[str, Any]]]:
    data = await service.get_inventory_alerts()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/donation-summary",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "donations:read", "finance:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_donation_summary(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_donation_summary()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/rescue-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "rescue:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_rescue_stats(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_rescue_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/medical-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "medical:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_medical_stats(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_medical_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/adoption-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "adoption:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_adoption_stats(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_adoption_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/volunteer-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[
        Depends(require_permission("system:admin", "volunteer:read", "volunteer:manage"))
    ],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_volunteer_stats(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_volunteer_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/notification-summary",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "notification:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_notification_summary(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_notification_summary()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/shelter-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "shelter:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_shelter_stats(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_shelter_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/foster-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "foster:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_foster_stats(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_foster_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/lost-found-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "lost_found:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_lost_found_stats(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_lost_found_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/grievance-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin", "grievance:read"))],
)
@cache_response(ttl_seconds=300, namespace="admin_dashboard")
async def get_grievance_stats(
    request: Request,
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_grievance_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/governance",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_role("super_admin"))],
)
async def get_governance_summary(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, Any]]:
    now = datetime.now(UTC)
    live = (User.deleted_at.is_(None),)
    by_role = (
        await db.execute(
            select(Role.name, func.count(func.distinct(User.id)))
            .join(UserRole, UserRole.role_id == Role.id)
            .join(User, User.id == UserRole.user_id)
            .where(*live, User.is_active.is_(True))
            .group_by(Role.name)
        )
    ).all()
    inactive = (
        await db.execute(select(func.count(User.id)).where(*live, User.is_active.is_(False)))
    ).scalar_one()
    locked = (
        await db.execute(select(func.count(User.id)).where(*live, User.locked_until > now))
    ).scalar_one()
    admins_without_mfa = (
        await db.execute(
            select(User.id, User.email, User.full_name)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                *live,
                User.is_active.is_(True),
                User.mfa_enabled.is_(False),
                Role.name.in_(("super_admin", "rescue_centre_admin")),
            )
            .distinct()
        )
    ).all()
    failed_logins = (
        await db.execute(
            select(func.count(AuthAuditLog.id)).where(
                AuthAuditLog.event_type == AuthAuditEventType.LOGIN_FAILED.value,
                AuthAuditLog.created_at >= now - timedelta(hours=24),
            )
        )
    ).scalar_one()
    last_backup = (
        await db.execute(
            select(func.max(AuthAuditLog.created_at)).where(
                AuthAuditLog.event_type == AuthAuditEventType.BACKUP_CREATED.value
            )
        )
    ).scalar_one()
    return ApiResponse(
        data={
            "users_by_role": {name: count for name, count in by_role},
            "active_users": sum(count for _, count in by_role),
            "inactive_users": inactive,
            "locked_accounts": locked,
            "admins_without_mfa": [
                {"id": str(uid), "email": email, "full_name": name}
                for uid, email, name in admins_without_mfa
            ],
            "failed_logins_24h": failed_logins,
            "last_backup_at": last_backup.isoformat() if last_backup else None,
        }
    )
