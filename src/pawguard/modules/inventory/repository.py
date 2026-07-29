"""Data access for the Inventory module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.inventory.models import InventoryItem, InventoryMovement, RequisitionOrder


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_item(self, item: InventoryItem) -> InventoryItem:
        self._session.add(item)
        await self._session.flush()
        return item

    async def get_item(self, item_id: uuid.UUID) -> InventoryItem | None:
        stmt = select(InventoryItem).where(InventoryItem.id == item_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_item_by_name(self, name: str) -> InventoryItem | None:
        stmt = select(InventoryItem).where(InventoryItem.name == name)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_items(self) -> Sequence[InventoryItem]:
        stmt = select(InventoryItem).order_by(InventoryItem.name.asc())
        return (await self._session.execute(stmt)).scalars().all()

    async def create_movement(self, movement: InventoryMovement) -> InventoryMovement:
        self._session.add(movement)
        await self._session.flush()
        return movement

    async def list_movements_by_item(self, item_id: uuid.UUID) -> Sequence[InventoryMovement]:
        stmt = select(InventoryMovement).where(InventoryMovement.item_id == item_id).order_by(InventoryMovement.created_at.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def create_requisition(self, req: RequisitionOrder) -> RequisitionOrder:
        self._session.add(req)
        await self._session.flush()
        return req

    async def get_requisition(self, req_id: uuid.UUID) -> RequisitionOrder | None:
        stmt = select(RequisitionOrder).where(RequisitionOrder.id == req_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_requisitions(self) -> Sequence[RequisitionOrder]:
        stmt = select(RequisitionOrder).order_by(RequisitionOrder.created_at.desc())
        return (await self._session.execute(stmt)).scalars().all()
