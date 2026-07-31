from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dashboards import service as dasvc

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get(
    "/rescue",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:rescue"))],
)
async def get_rescue_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.rescue_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/shelter",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:shelter"))],
)
async def get_shelter_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.shelter_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/medical",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:medical"))],
)
async def get_medical_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.medical_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/adoption",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:adoption"))],
)
async def get_adoption_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.adoption_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/foster",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:foster"))],
)
async def get_foster_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.foster_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/volunteer",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:volunteer"))],
)
async def get_volunteer_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.volunteer_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/inventory",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:inventory"))],
)
async def get_inventory_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.inventory_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/finance",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:finance"))],
)
async def get_finance_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.finance_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/donor",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:donor"))],
)
async def get_donor_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.donor_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/staff",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_staff_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.staff_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/executive",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_executive_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.executive_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/public",
    response_model=ApiResponse[dict[str, Any]],
)
async def get_public_dashboard(
    db: AsyncSession = Depends(get_db),
):
    data = await dasvc.public_dashboard(db)
    return ApiResponse(data=data)


@router.get(
    "/operations",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_operations_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await dasvc.operations_dashboard(db)
    return ApiResponse(data=data)
