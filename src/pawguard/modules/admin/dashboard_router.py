"""Admin dashboard endpoints: analytics, metrics, system overview (RULE-004)."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.admin.dashboard_repository import DashboardRepository
from pawguard.modules.admin.dashboard_service import DashboardService
from pawguard.modules.auth.rbac import require_permission
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
async def get_system_metrics(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, int]]:
    metrics = await service.get_system_metrics()
    return ApiResponse(data=metrics)


@admin_dashboard_router.get(
    "/summary",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_summary(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_summary()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/kpis",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_kpis(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_kpis()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/charts",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_charts(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_charts()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/recent-activity",
    response_model=ApiResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_recent_activity(
    limit: int = Query(20, ge=1, le=100),
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[list[dict[str, Any]]]:
    data = await service.get_recent_activity(limit=limit)
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/inventory-alerts",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_inventory_alerts(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_inventory_alerts()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/donation-summary",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_donation_summary(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_donation_summary()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/rescue-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_rescue_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_rescue_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/medical-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_medical_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_medical_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/adoption-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_adoption_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_adoption_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/volunteer-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_volunteer_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_volunteer_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/notification-summary",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_notification_summary(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_notification_summary()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/shelter-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_shelter_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_shelter_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/foster-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_foster_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_foster_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/lost-found-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_lost_found_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_lost_found_stats()
    return ApiResponse(data=data)


@admin_dashboard_router.get(
    "/grievance-stats",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_grievance_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_grievance_stats()
    return ApiResponse(data=data)
