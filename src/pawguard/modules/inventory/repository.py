"""Data access for the Inventory module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.inventory.models import (
    InventoryItem,
    InventoryMovement,
    ItemCategory,
    MovementType,
    RequisitionOrder,
    RequisitionStatus,
)


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_item(self, item: InventoryItem) -> InventoryItem:
        self._session.add(item)
        await self._session.flush()
        return item

    async def get_item(self, item_id: uuid.UUID) -> InventoryItem | None:
        stmt = select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_items_by_ids(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, InventoryItem | None]:
        """Fetch multiple items by ID in a single query.
        
        Returns a dict mapping item_id -> item (or None if not found).
        More efficient than calling get_item in a loop (N+1 problem).
        """
        stmt = select(InventoryItem).where(
            InventoryItem.id.in_(item_ids),
            InventoryItem.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return {row.id: row for row in result.scalars().all()}

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

    async def list_movements_by_item(
        self, item_id: uuid.UUID,
    ) -> Sequence[InventoryMovement]:
        stmt = (
            select(InventoryMovement)
            .where(InventoryMovement.item_id == item_id)
            .order_by(InventoryMovement.created_at.desc())
        )
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

    async def list_items_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        category: ItemCategory | None = None,
    ) -> tuple[Sequence[InventoryItem], int]:
        stmt = select(InventoryItem).where(InventoryItem.deleted_at.is_(None))

        search_filter = build_search_filter(InventoryItem, search_term, ("name", "category"))
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if category is not None:
            stmt = stmt.where(InventoryItem.category == category)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        valid_fields = {"name", "quantity", "category", "created_at", "updated_at", "expiry_date"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_movements_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        item_id: uuid.UUID | None = None,
        movement_type: MovementType | None = None,
    ) -> tuple[Sequence[InventoryMovement], int]:
        stmt = select(InventoryMovement)

        if item_id is not None:
            stmt = stmt.where(InventoryMovement.item_id == item_id)
        if movement_type is not None:
            stmt = stmt.where(InventoryMovement.movement_type == movement_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        valid_fields = {"created_at", "quantity", "movement_type"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_requisitions_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        status: RequisitionStatus | None = None,
    ) -> tuple[Sequence[RequisitionOrder], int]:
        stmt = select(RequisitionOrder)

        if status is not None:
            stmt = stmt.where(RequisitionOrder.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        valid_fields = {"created_at", "status", "quantity", "updated_at"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def soft_delete_item(self, item_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.id == item_id, InventoryItem.deleted_at.is_(None))
        )
        item = (await self._session.execute(stmt)).scalar_one_or_none()
        if item is None:
            return False
        item.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def bulk_delete_items(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.id.in_(ids), InventoryItem.deleted_at.is_(None))
        )
        items = (await self._session.execute(stmt)).scalars().all()
        for item in items:
            item.deleted_at = now
        await self._session.flush()
        return len(items)

    async def bulk_update_requisition_status(
        self,
        ids: list[uuid.UUID],
        status: RequisitionStatus,
    ) -> int:
        stmt = (
            update(RequisitionOrder)
            .where(RequisitionOrder.id.in_(ids))
            .values(status=status)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[attr-defined,no-any-return]
