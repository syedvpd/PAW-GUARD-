"""InventoryService: owns stock levels, movement logs, and requisition flows.

Adheres to RULE-003.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.logging import get_logger
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
    Supplier,
)
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.schemas import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    InventoryMovementCreate,
    InventoryMovementResponse,
    RequisitionOrderCreate,
    RequisitionOrderResponse,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)
from pawguard.modules.notifications.schemas import BroadcastCreate
from pawguard.modules.notifications.service import NotificationService
from pawguard.services.audit_service import AuditService

logger = get_logger(__name__)


class InventoryService:
    def __init__(
        self,
        repository: InventoryRepository,
        audit_service: AuditService | None = None,
        notification_service: NotificationService | None = None,
        redis: Any | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service
        self._notification_svc = notification_service
        self._redis = redis

    async def _invalidate_dashboard_cache(self) -> None:
        if self._redis:
            try:
                await self._redis.delete(
                    "cache:dashboard:inventory",
                    "cache:dashboard:operations",
                )
            except Exception:
                pass

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
        await self._invalidate_dashboard_cache()
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

        if payload.movement_type in (MovementType.CHECK_OUT, MovementType.CONSUMPTION):
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
        await self._invalidate_dashboard_cache()
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
        # Workflow 8: when stock falls to/below the reorder threshold, alert
        # inventory staff and administrators so a purchase requisition can be
        # raised (avoids silent stock-outs of medicine/food).
        if item.quantity <= item.reorder_threshold:
            await self._alert_low_stock(item)
        return movement

    async def _alert_low_stock(self, item: InventoryItem) -> None:
        if self._notification_svc is None:
            return
        try:
            await self._notification_svc.broadcast(
                payload=BroadcastCreate(
                    title=f"Low stock alert: {item.name}",
                    body=(
                        f"Stock for '{item.name}' is at {item.quantity} {item.unit} "
                        f"(reorder threshold {item.reorder_threshold} {item.unit}). "
                        "Please raise a purchase requisition."
                    ),
                    notification_type="inventory_low_stock",
                    action_url="/inventory/requisitions",
                    target_roles=["inventory_manager", "rescue_centre_admin"],
                ),
                user_ids=[],
                actor_id=None,
            )
        except Exception:  # pragma: no cover - alerting must never break stock ops
            logger.warning(
                "Failed to send low-stock alert for item %s", item.id, exc_info=True
            )

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

    async def update_item(
        self,
        item_id: uuid.UUID,
        payload: "InventoryItemUpdate",
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> InventoryItem:
        item = await self._repo.get_item(item_id)
        if item is None:
            raise NotFoundError("Inventory item not found.")
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "name" in update_data and update_data["name"] != item.name:
            existing = await self._repo.get_item_by_name(update_data["name"])
            if existing is not None:
                raise ConflictError(
                    f"Inventory item '{update_data['name']}' already registered."
                )
        updated = await self._repo.update_item(item, **update_data)
        await self._invalidate_dashboard_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "item_id": str(item_id),
                    "changes": update_data,
                },
            )
        return updated

    async def get_items_by_ids(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, InventoryItem | None]:
        """Fetch multiple items by ID in a single query.

        Returns a dict mapping item_id -> item (or None if not found).
        More efficient than calling get_item in a loop (N+1 problem).
        """
        return await self._repo.get_items_by_ids(item_ids)

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
        await self._invalidate_dashboard_cache()
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
        await self._invalidate_dashboard_cache()
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

    # ── Supplier CRUD ─────────────────────────────────────────────────

    async def create_supplier(
        self,
        payload: SupplierCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Supplier:
        existing = await self._repo.get_supplier_by_name(payload.name)
        if existing is not None:
            raise ConflictError(f"Supplier '{payload.name}' already registered.")
        supplier = Supplier(
            name=payload.name,
            contact_person=payload.contact_person,
            email=payload.email,
            phone=payload.phone,
            address=payload.address,
            gst_number=payload.gst_number,
            pan_number=payload.pan_number,
            bank_details=payload.bank_details,
            payment_terms=payload.payment_terms,
            notes=payload.notes,
        )
        result = await self._repo.create_supplier(supplier)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"supplier_id": str(result.id), "name": payload.name},
            )
        return result

    async def get_supplier(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = await self._repo.get_supplier_by_id(supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found.")
        return supplier

    async def update_supplier(
        self,
        supplier_id: uuid.UUID,
        payload: SupplierUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Supplier:
        supplier = await self._repo.get_supplier_by_id(supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found.")
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "name" in update_data and update_data["name"] != supplier.name:
            existing = await self._repo.get_supplier_by_name(update_data["name"])
            if existing is not None:
                raise ConflictError(
                    f"Supplier '{update_data['name']}' already registered."
                )
        updated = await self._repo.update_supplier(supplier, **update_data)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "supplier_id": str(supplier_id),
                    "changes": update_data,
                },
            )
        return updated

    async def list_suppliers_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResponse[SupplierResponse]:
        suppliers, total = await self._repo.list_suppliers_paginated(
            page_params, sort, search_term=search_term, is_active=is_active,
        )
        return PaginatedResponse(
            data=[SupplierResponse.model_validate(s) for s in suppliers],
            meta=build_pagination_meta(total=total, params=page_params),
        )

    async def soft_delete_supplier(
        self,
        supplier_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        deleted = await self._repo.soft_delete_supplier(supplier_id)
        if not deleted:
            raise NotFoundError("Supplier not found.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"supplier_id": str(supplier_id)},
            )
