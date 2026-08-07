"""InventoryService: owns stock levels, movement logs, and requisition flows.

Adheres to RULE-003.
"""

import uuid
from collections.abc import Sequence

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.inventory.models import (
    InventoryItem,
    InventoryMovement,
    ItemCategory,
    MovementType,
    RequisitionOrder,
    RequisitionStatus,
)
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.schemas import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryMovementCreate,
    InventoryMovementResponse,
    RequisitionOrderCreate,
    RequisitionOrderResponse,
)
from pawguard.services.audit_service import AuditService


class InventoryService:
    def __init__(
        self,
        repository: InventoryRepository,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service

    async def create_item(
        self,
        payload: InventoryItemCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> InventoryItem:
        existing = await self._repo.get_item_by_name(payload.name)
        if existing is not None:
            raise ConflictError(f"Inventory item '{payload.name}' already registered.")

        item = InventoryItem(
            name=payload.name,
            category=payload.category,
            quantity=payload.quantity,
            unit=payload.unit,
            reorder_threshold=payload.reorder_threshold,
            expiry_date=payload.expiry_date,
            unit_cost=payload.unit_cost,
        )
        result = await self._repo.create_item(item)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"item_id": str(result.id)},
            )
        return result

    async def record_movement(
        self,
        user_id: uuid.UUID,
        payload: InventoryMovementCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> InventoryMovement:
        item = await self._repo.get_item(payload.item_id)
        if item is None:
            raise NotFoundError("Inventory item not found.")

        qty_change = payload.quantity
        from datetime import date

        if payload.movement_type == MovementType.CHECK_OUT:
            # Expiry date enforcement (PRD 3.12)
            if item.expiry_date is not None and item.expiry_date < date.today():
                raise ConflictError(
                    f"Cannot check out expired inventory item '{item.name}'. "
                    f"Expired on: {item.expiry_date}"
                )
            if item.quantity < qty_change:
                raise ConflictError(
                    f"Insufficient stock for '{item.name}'. "
                    f"Available: {item.quantity} {item.unit}, "
                    f"Requested: {qty_change}"
                )
            item.quantity -= qty_change
        elif payload.movement_type == MovementType.CHECK_IN:
            item.quantity += qty_change
        else:
            item.quantity = qty_change

        movement = InventoryMovement(
            item_id=payload.item_id,
            moved_by=user_id,
            movement_type=payload.movement_type,
            quantity=qty_change,
            notes=payload.notes,
            reference_type=payload.reference_type,
            reference_id=payload.reference_id,
        )
        await self._repo.create_movement(movement)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_STOCK_ADJUSTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "movement_id": str(movement.id),
                    "item_id": str(item.id),
                    "quantity": qty_change,
                    "movement_type": payload.movement_type.value,
                },
            )
        return movement

    async def create_requisition(
        self,
        user_id: uuid.UUID,
        payload: RequisitionOrderCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RequisitionOrder:
        item = await self._repo.get_item(payload.item_id)
        if item is None:
            raise NotFoundError("Inventory item not found.")

        req = RequisitionOrder(
            item_id=payload.item_id,
            requester_id=user_id,
            quantity=payload.quantity,
            status=RequisitionStatus.PENDING,
        )
        return await self._repo.create_requisition(req)

    async def update_requisition_status(
        self,
        user_id: uuid.UUID,
        req_id: uuid.UUID,
        status: RequisitionStatus,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RequisitionOrder:
        req = await self._repo.get_requisition(req_id)
        if req is None:
            raise NotFoundError("Requisition order not found.")

        if req.status == RequisitionStatus.RECEIVED:
            raise ConflictError("Requisition order is already marked as received.")

        if status == RequisitionStatus.RECEIVED:
            item = await self._repo.get_item(req.item_id)
            if item is None:
                raise NotFoundError("Associated inventory item not found.")

            movement = InventoryMovement(
                item_id=req.item_id,
                moved_by=user_id,
                movement_type=MovementType.CHECK_IN,
                quantity=req.quantity,
                notes=f"Auto-delivered from Requisition Order #{req.id}",
            )
            item.quantity += req.quantity
            await self._repo.create_movement(movement)

        req.status = status
        await self._repo._session.flush()
        await self._repo._session.refresh(req)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_STOCK_ADJUSTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"requisition_id": str(req.id), "status": status.value},
            )
        return req

    async def get_item(self, item_id: uuid.UUID) -> InventoryItem:
        item = await self._repo.get_item(item_id)
        if item is None:
            raise NotFoundError("Inventory item not found.")
        return item

    async def list_items(self) -> Sequence[InventoryItem]:
        return await self._repo.list_items()

    async def list_movements(self, item_id: uuid.UUID) -> Sequence[InventoryMovement]:
        return await self._repo.list_movements_by_item(item_id)

    async def list_requisitions(self) -> Sequence[RequisitionOrder]:
        return await self._repo.list_requisitions()

    async def list_items_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        category: ItemCategory | None = None,
    ) -> PaginatedResponse[InventoryItemResponse]:
        items, total = await self._repo.list_items_paginated(
            page_params, sort, search_term=search_term, category=category,
        )
        return PaginatedResponse(
            data=list(items),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def list_movements_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        item_id: uuid.UUID | None = None,
        movement_type: MovementType | None = None,
    ) -> PaginatedResponse[InventoryMovementResponse]:
        if item_id is not None:
            item = await self._repo.get_item(item_id)
            if item is None:
                raise NotFoundError("Inventory item not found.")
        movements, total = await self._repo.list_movements_paginated(
            page_params, sort, item_id=item_id, movement_type=movement_type,
        )
        return PaginatedResponse(
            data=list(movements),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def list_requisitions_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        status: RequisitionStatus | None = None,
    ) -> PaginatedResponse[RequisitionOrderResponse]:
        reqs, total = await self._repo.list_requisitions_paginated(
            page_params, sort, status=status,
        )
        return PaginatedResponse(
            data=list(reqs),
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def soft_delete_item(
        self,
        item_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        deleted = await self._repo.soft_delete_item(item_id)
        if not deleted:
            raise NotFoundError("Inventory item not found.")
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"item_id": str(item_id)},
            )

    async def bulk_delete_items(
        self,
        ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_delete_items(ids)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"item_ids": [str(i) for i in ids], "count": count},
            )
        return count

    async def bulk_update_requisition_status(
        self,
        ids: list[uuid.UUID],
        status: RequisitionStatus,
    ) -> int:
        return await self._repo.bulk_update_requisition_status(ids, status)
