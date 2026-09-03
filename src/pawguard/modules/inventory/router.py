"""API router for the Inventory module. Routers only validate and call services (RULE-004)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.exceptions import ForbiddenError, parse_enum
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import has_permission, require_permission
from pawguard.modules.inventory.models import ItemCategory, MovementType, RequisitionStatus
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.schemas import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    InventoryMovementCreate,
    InventoryMovementResponse,
    RequisitionOrderCreate,
    RequisitionOrderResponse,
    RequisitionStatusUpdate,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)
from pawguard.modules.inventory.service import InventoryService
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.redis.client import RedisClient, get_redis
from pawguard.services.audit_service import AuditService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/inventory", tags=["inventory"])


def get_inventory_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    arq_pool: Any = Depends(get_arq_pool),
    redis: RedisClient = Depends(get_redis),
) -> InventoryService:
    repo = InventoryRepository(db)
    notification_repo = NotificationRepository(db)
    notification_svc = NotificationService(repository=notification_repo, arq_pool=arq_pool)
    return InventoryService(
        repo,
        audit_service=audit,
        notification_service=notification_svc,
        redis=redis,
    )


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
    ip = request.client.host if request.client else None
    item = await service.create_item(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=InventoryItemResponse.model_validate(item),
        message="Inventory item created.",
    )


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


@router.put(
    "/items/{item_id}",
    response_model=ApiResponse[InventoryItemResponse],
    dependencies=[Depends(require_permission("inventory:update"))],
)
async def update_item(
    item_id: uuid.UUID,
    payload: InventoryItemUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[InventoryItemResponse]:
    ip = request.client.host if request.client else None
    item = await service.update_item(
        item_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=InventoryItemResponse.model_validate(item),
        message="Inventory item updated.",
    )


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
    ip = request.client.host if request.client else None
    movement = await service.record_movement(
        current_user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=InventoryMovementResponse.model_validate(movement),
        message="Stock movement recorded.",
    )


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
        page,
        sort,
        item_id=item_id,
        movement_type=movement_type,
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
    ip = request.client.host if request.client else None
    req = await service.create_requisition(
        current_user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=RequisitionOrderResponse.model_validate(req),
        message="Requisition submitted.",
    )


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
    # Workflow 8: the requisition APPROVAL step requires administrator
    # authority; the requesting Inventory Manager cannot self-approve. Other
    # transitions (reject, mark received) remain with inventory:update.
    if payload.status == RequisitionStatus.APPROVED and not has_permission(
        current_user.user, "system:admin"
    ):
        raise ForbiddenError("Requisition approval requires administrator privileges.")
    ip = request.client.host if request.client else None
    req = await service.update_requisition_status(
        current_user.id,
        req_id,
        payload.status,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=RequisitionOrderResponse.model_validate(req),
        message="Requisition status updated.",
    )


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
    ip = request.client.host if request.client else None
    await service.soft_delete_item(
        item_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
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
    ip = request.client.host if request.client else None
    deleted = await service.bulk_delete_items(
        payload.ids,
        actor_id=current_user.id,
        ip_address=ip,
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
        payload.ids,
        parse_enum(RequisitionStatus, payload.status),
    )
    return BulkStatusUpdateResponse(
        message=f"{updated} requisitions updated.",
        updated_count=updated,
    )


# ── Supplier / Vendor Management ────────────────────────────────────────


@router.post(
    "/suppliers",
    response_model=ApiResponse[SupplierResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("inventory:create"))],
)
async def create_supplier(
    payload: SupplierCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[SupplierResponse]:
    ip = request.client.host if request.client else None
    supplier = await service.create_supplier(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=SupplierResponse.model_validate(supplier),
        message="Supplier created.",
    )


@router.get(
    "/suppliers",
    response_model=PaginatedResponse[SupplierResponse],
    dependencies=[Depends(require_permission("inventory:read"))],
)
async def list_suppliers(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = None,
    is_active: bool | None = None,
    service: InventoryService = Depends(get_inventory_service),
) -> PaginatedResponse[SupplierResponse]:
    return await service.list_suppliers_paginated(page, sort, search, is_active)


@router.get(
    "/suppliers/{supplier_id}",
    response_model=ApiResponse[SupplierResponse],
    dependencies=[Depends(require_permission("inventory:read"))],
)
async def get_supplier(
    supplier_id: uuid.UUID,
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[SupplierResponse]:
    supplier = await service.get_supplier(supplier_id)
    return ApiResponse(data=SupplierResponse.model_validate(supplier))


@router.put(
    "/suppliers/{supplier_id}",
    response_model=ApiResponse[SupplierResponse],
    dependencies=[Depends(require_permission("inventory:update"))],
)
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[SupplierResponse]:
    ip = request.client.host if request.client else None
    supplier = await service.update_supplier(
        supplier_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=SupplierResponse.model_validate(supplier),
        message="Supplier updated.",
    )


@router.delete(
    "/suppliers/{supplier_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("inventory:update"))],
)
async def delete_supplier(
    supplier_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_supplier(
        supplier_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="Supplier deleted.")
