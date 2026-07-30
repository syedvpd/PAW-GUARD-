"""API router for fleet management (RULE-004)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.fleet.models import VehicleStatus
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.schemas import (
    MaintenanceCreate,
    MaintenanceResponse,
    VehicleCreate,
    VehicleResponse,
    VehicleStatusUpdate,
    VehicleUpdate,
)
from pawguard.modules.fleet.service import FleetService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/fleet", tags=["fleet"])


def get_fleet_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> FleetService:
    return FleetService(FleetRepository(db), audit_service=audit)


@router.post(
    "/vehicles",
    response_model=ApiResponse[VehicleResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vehicle:update"))],
)
async def create_vehicle(
    payload: VehicleCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FleetService = Depends(get_fleet_service),
) -> ApiResponse[VehicleResponse]:
    vehicle = await service.create_vehicle(
        payload, actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data=VehicleResponse.model_validate(vehicle), message="Vehicle registered.")


@router.get(
    "/vehicles",
    response_model=PaginatedResponse[VehicleResponse],
    dependencies=[Depends(require_permission("vehicle:read"))],
)
async def list_vehicles(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by make/model, license plate"),
    status: VehicleStatus | None = Query(None, description="Filter by status"),
    service: FleetService = Depends(get_fleet_service),
) -> PaginatedResponse[VehicleResponse]:
    return await service.list_vehicles_paginated(
        page=page,
        sort=sort,
        search_term=search,
        status=status,
    )


@router.get(
    "/vehicles/{vehicle_id}",
    response_model=ApiResponse[VehicleResponse],
    dependencies=[Depends(require_permission("vehicle:read"))],
)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    service: FleetService = Depends(get_fleet_service),
) -> ApiResponse[VehicleResponse]:
    vehicle = await service.get_vehicle(vehicle_id)
    return ApiResponse(data=VehicleResponse.model_validate(vehicle))


@router.put(
    "/vehicles/{vehicle_id}",
    response_model=ApiResponse[VehicleResponse],
    dependencies=[Depends(require_permission("vehicle:update"))],
)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    payload: VehicleUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FleetService = Depends(get_fleet_service),
) -> ApiResponse[VehicleResponse]:
    vehicle = await service.update_vehicle(
        vehicle_id, payload, actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data=VehicleResponse.model_validate(vehicle), message="Vehicle updated.")


@router.patch(
    "/vehicles/{vehicle_id}/status",
    response_model=ApiResponse[VehicleResponse],
    dependencies=[Depends(require_permission("vehicle:update"))],
)
async def update_vehicle_status(
    vehicle_id: uuid.UUID,
    payload: VehicleStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FleetService = Depends(get_fleet_service),
) -> ApiResponse[VehicleResponse]:
    vehicle = await service.update_vehicle_status(
        vehicle_id, payload.status, actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=VehicleResponse.model_validate(vehicle),
        message="Vehicle status updated successfully.",
    )


@router.delete(
    "/vehicles/{vehicle_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("vehicle:update"))],
)
async def soft_delete_vehicle(
    vehicle_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FleetService = Depends(get_fleet_service),
) -> ApiResponse[None]:
    await service.soft_delete_vehicle(
        vehicle_id,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(message="Vehicle deleted successfully.")


@router.post(
    "/maintenance",
    response_model=ApiResponse[MaintenanceResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vehicle:update"))],
)
async def log_maintenance(
    payload: MaintenanceCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FleetService = Depends(get_fleet_service),
) -> ApiResponse[MaintenanceResponse]:
    record = await service.log_maintenance(
        payload,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=MaintenanceResponse.model_validate(record),
        message="Maintenance logged.",
    )


@router.get(
    "/vehicles/{vehicle_id}/maintenance",
    response_model=PaginatedResponse[MaintenanceResponse],
    dependencies=[Depends(require_permission("vehicle:read"))],
)
async def list_maintenance(
    vehicle_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    service: FleetService = Depends(get_fleet_service),
) -> PaginatedResponse[MaintenanceResponse]:
    return await service.list_maintenance_paginated(
        page=page,
        sort=sort,
        vehicle_id=vehicle_id,
    )


@router.post(
    "/bulk/status-update",
    response_model=ApiResponse[BulkStatusUpdateResponse],
    dependencies=[Depends(require_permission("vehicle:update"))],
)
async def bulk_update_vehicle_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FleetService = Depends(get_fleet_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    updated = await service.bulk_update_status(
        payload.ids,
        VehicleStatus(payload.status),
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkStatusUpdateResponse(
            message=f"{updated} vehicle(s) status updated.",
            updated_count=updated,
        ),
    )


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("vehicle:update"))],
)
async def bulk_delete_vehicles(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FleetService = Depends(get_fleet_service),
) -> ApiResponse[BulkDeleteResponse]:
    deleted = await service.bulk_soft_delete(
        payload.ids,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} vehicle(s) deleted.",
            deleted_count=deleted,
        ),
    )
