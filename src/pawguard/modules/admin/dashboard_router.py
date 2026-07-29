"""Admin dashboard endpoints: analytics, metrics, system overview.

Each endpoint enforces RBAC permissions (RULE-004) to ensure only authorized
administrators can view system-level analytics.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.admin.dashboard_repository import DashboardRepository
from pawguard.modules.admin.dashboard_service import DashboardService
from pawguard.modules.auth.rbac import require_permission

admin_dashboard_router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


def get_dashboard_service(db: AsyncSession = Depends(get_db)) -> DashboardService:
    repo = DashboardRepository(db)
    return DashboardService(repo)


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