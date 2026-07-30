"""API router for the Inventory module. Routers only validate and call services (RULE-004)."""

import uuid

from fastapi import APIRouter, Depends, Request, status
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
from pawguard.modules.inventory.models import ItemCategory, MovementType, RequisitionStatus
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.schemas import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryMovementCreate,
    InventoryMovementResponse,
    RequisitionOrderCreate,
    RequisitionOrderResponse,
    RequisitionStatusUpdate,
)
from pawguard.modules.inventory.service import InventoryService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/inventory", tags=["inventory"])


def get_inventory_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> InventoryService:
    return InventoryService(InventoryRepository(db), audit_service=audit)


@router.post(
    "/items",
    response_model=ApiResponse[InventoryItemResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("inventory:create"))],
)
async def create_item(
    payload: InventoryItemCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[InventoryItemResponse]:
    item = await service.create_item(payload, actor_id=current_user.id, ip_address=request.client.host if request.client else None)
    return ApiResponse(data=InventoryItemResponse.model_validate(item), message="Inventory item created.")


@router.get(
    "/items",
    response_model=PaginatedResponse[InventoryItemResponse],
    dependencies=[Depends(require_permission("inventory:read"))],
)
async def list_items(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    category: ItemCategory | None = None,
    service: InventoryService = Depends(get_inventory_service),
) -> PaginatedResponse[InventoryItemResponse]:
    result = await service.list_items_paginated(page, sort, search_term=search, category=category)
    return PaginatedResponse(
        data=[InventoryItemResponse.model_validate(i) for i in result.data],
        meta=result.meta,
    )


@router.get(
    "/items/{item_id}",
    response_model=ApiResponse[InventoryItemResponse],
    dependencies=[Depends(require_permission("inventory:read"))],
)
async def get_item(
    item_id: uuid.UUID,
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[InventoryItemResponse]:
    item = await service.get_item(item_id)
    return ApiResponse(data=InventoryItemResponse.model_validate(item))


@router.post(
    "/movements",
    response_model=ApiResponse[InventoryMovementResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("inventory:update"))],
)
async def record_movement(
    payload: InventoryMovementCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[InventoryMovementResponse]:
    movement = await service.record_movement(
        current_user.id, payload, actor_id=current_user.id, ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data=InventoryMovementResponse.model_validate(movement), message="Stock movement recorded.")


@router.get(
    "/items/{item_id}/movements",
    response_model=PaginatedResponse[InventoryMovementResponse],
    dependencies=[Depends(require_permission("inventory:read"))],
)
async def list_movements(
    item_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    movement_type: MovementType | None = None,
    service: InventoryService = Depends(get_inventory_service),
) -> PaginatedResponse[InventoryMovementResponse]:
    result = await service.list_movements_paginated(
        page, sort, item_id=item_id, movement_type=movement_type,
    )
    return PaginatedResponse(
        data=[InventoryMovementResponse.model_validate(m) for m in result.data],
        meta=result.meta,
    )


@router.post(
    "/requisitions",
    response_model=ApiResponse[RequisitionOrderResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("inventory:create"))],
)
async def create_requisition(
    payload: RequisitionOrderCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[RequisitionOrderResponse]:
    req = await service.create_requisition(
        current_user.id, payload, actor_id=current_user.id, ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data=RequisitionOrderResponse.model_validate(req), message="Requisition submitted.")


@router.get(
    "/requisitions",
    response_model=PaginatedResponse[RequisitionOrderResponse],
    dependencies=[Depends(require_permission("inventory:read"))],
)
async def list_requisitions(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    status: RequisitionStatus | None = None,
    service: InventoryService = Depends(get_inventory_service),
) -> PaginatedResponse[RequisitionOrderResponse]:
    result = await service.list_requisitions_paginated(page, sort, status=status)
    return PaginatedResponse(
        data=[RequisitionOrderResponse.model_validate(r) for r in result.data],
        meta=result.meta,
    )


@router.put(
    "/requisitions/{req_id}/status",
    response_model=ApiResponse[RequisitionOrderResponse],
    dependencies=[Depends(require_permission("inventory:update"))],
)
async def update_requisition_status(
    req_id: uuid.UUID,
    payload: RequisitionStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[RequisitionOrderResponse]:
    req = await service.update_requisition_status(
        current_user.id, req_id, payload.status, actor_id=current_user.id, ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data=RequisitionOrderResponse.model_validate(req), message="Requisition status updated.")


@router.delete(
    "/items/{item_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("inventory:update"))],
)
async def delete_item(
    item_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[None]:
    await service.soft_delete_item(item_id, actor_id=current_user.id, ip_address=request.client.host if request.client else None)
    return ApiResponse(message="Inventory item deleted.")


@router.post(
    "/items/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("inventory:update"))],
)
async def bulk_delete_items(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> BulkDeleteResponse:
    deleted = await service.bulk_delete_items(
        payload.ids, actor_id=current_user.id, ip_address=request.client.host if request.client else None,
    )
    return BulkDeleteResponse(
        message=f"{deleted} items deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/requisitions/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("inventory:update"))],
)
async def bulk_update_requisition_status(
    payload: BulkStatusUpdateRequest,
    service: InventoryService = Depends(get_inventory_service),
) -> BulkStatusUpdateResponse:
    updated = await service.bulk_update_requisition_status(
        payload.ids, RequisitionStatus(payload.status),
    )
    return BulkStatusUpdateResponse(
        message=f"{updated} requisitions updated.",
        updated_count=updated,
    )
