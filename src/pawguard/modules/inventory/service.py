"""InventoryService: owns all stock levels, check-in/check-out logs, reorder threshold alerts, and requisition flows (RULE-003)."""

import uuid
from typing import Sequence

from pawguard.core.exceptions import ConflictError, NotFoundError
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
    InventoryMovementCreate,
    RequisitionOrderCreate,
)


class InventoryService:
    def __init__(self, repository: InventoryRepository) -> None:
        self._repo = repository

    async def create_item(self, payload: InventoryItemCreate) -> InventoryItem:
        # Check if item exists
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
        )
        return await self._repo.create_item(item)

    async def record_movement(self, user_id: uuid.UUID, payload: InventoryMovementCreate) -> InventoryMovement:
        item = await self._repo.get_item(payload.item_id)
        if item is None:
            raise NotFoundError("Inventory item not found.")

        qty_change = payload.quantity

        # Business Rule validation
        if payload.movement_type == MovementType.CHECK_OUT:
            if item.quantity < qty_change:
                raise ConflictError(
                    f"Insufficient stock for '{item.name}'. Available: {item.quantity} {item.unit}, Requested: {qty_change}"
                )
            # Subtract
            item.quantity -= qty_change
        elif payload.movement_type == MovementType.CHECK_IN:
            # Add
            item.quantity += qty_change
        else:  # ADJUSTMENT
            item.quantity = qty_change  # Direct override

        movement = InventoryMovement(
            item_id=payload.item_id,
            moved_by=user_id,
            movement_type=payload.movement_type,
            quantity=qty_change,
            notes=payload.notes,
        )
        await self._repo.create_movement(movement)
        await self._repo._session.flush()
        return movement

    async def create_requisition(self, user_id: uuid.UUID, payload: RequisitionOrderCreate) -> RequisitionOrder:
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

    async def update_requisition_status(self, user_id: uuid.UUID, req_id: uuid.UUID, status: RequisitionStatus) -> RequisitionOrder:
        req = await self._repo.get_requisition(req_id)
        if req is None:
            raise NotFoundError("Requisition order not found.")

        if req.status == RequisitionStatus.RECEIVED:
            raise ConflictError("Requisition order is already marked as received.")

        # Business Rule transition: if status becomes RECEIVED, automatically add to inventory quantity!
        if status == RequisitionStatus.RECEIVED:
            item = await self._repo.get_item(req.item_id)
            if item is None:
                raise NotFoundError("Associated inventory item not found.")

            # Create Check-in movement
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
