"""Data access for the Inventory module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.inventory.models import (
    InventoryItem,
    InventoryItemSupplier,
    InventoryMovement,
    ItemCategory,
    MovementType,
    RequisitionOrder,
    RequisitionStatus,
    Supplier,
)
from pawguard.modules.shelter.models import ShelterFacility


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

    async def get_item_for_update(self, item_id: uuid.UUID) -> InventoryItem | None:
        stmt = select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.deleted_at.is_(None),
        )
        if self._session.bind and self._session.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_items_by_ids(
        self, item_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, InventoryItem | None]:
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

    async def get_item_by_name(
        self, name: str, facility_id: uuid.UUID | None = None
    ) -> InventoryItem | None:
        facility_filter = (
            InventoryItem.facility_id.is_(None)
            if facility_id is None
            else InventoryItem.facility_id == facility_id
        )
        stmt = select(InventoryItem).where(
            InventoryItem.name == name,
            facility_filter,
            InventoryItem.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def facility_exists(self, facility_id: uuid.UUID) -> bool:
        stmt = select(ShelterFacility.id).where(
            ShelterFacility.id == facility_id,
            ShelterFacility.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def stock_totals(self) -> tuple[int, float, float]:
        stmt = select(
            func.count(InventoryItem.id),
            func.coalesce(
                func.sum(func.greatest(InventoryItem.quantity, 0) * InventoryItem.unit_cost), 0
            ),
            func.coalesce(func.avg(InventoryItem.unit_cost), 0),
        ).where(InventoryItem.deleted_at.is_(None))
        count, value, avg_cost = (await self._session.execute(stmt)).one()
        return int(count), float(value), float(avg_cost)

    async def list_out_of_stock(self) -> Sequence[InventoryItem]:
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.deleted_at.is_(None), InventoryItem.quantity <= 0)
            .order_by(InventoryItem.name.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_low_stock(self) -> Sequence[InventoryItem]:
        stmt = (
            select(InventoryItem)
            .where(
                InventoryItem.deleted_at.is_(None),
                InventoryItem.quantity > 0,
                InventoryItem.quantity <= InventoryItem.reorder_threshold,
            )
            .order_by(
                (InventoryItem.quantity / func.nullif(InventoryItem.reorder_threshold, 0)).asc()
            )
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_expiring(self, cutoff: date) -> Sequence[InventoryItem]:
        stmt = (
            select(InventoryItem)
            .where(
                InventoryItem.deleted_at.is_(None),
                InventoryItem.expiry_date.is_not(None),
                InventoryItem.expiry_date <= cutoff,
            )
            .order_by(InventoryItem.expiry_date.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def update_item(self, item: InventoryItem, **kwargs: object) -> InventoryItem:
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def list_items(self) -> Sequence[InventoryItem]:
        stmt = select(InventoryItem).order_by(InventoryItem.name.asc())
        return (await self._session.execute(stmt)).scalars().all()

    async def create_movement(self, movement: InventoryMovement) -> InventoryMovement:
        self._session.add(movement)
        await self._session.flush()
        return movement

    async def list_movements_by_item(
        self,
        item_id: uuid.UUID,
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
        facility_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[InventoryItem], int]:
        filters = [InventoryItem.deleted_at.is_(None)]
        if facility_id is not None:
            filters.append(InventoryItem.facility_id == facility_id)

        search_filter = build_search_filter(InventoryItem, search_term, ("name", "category"))
        if search_filter is not None:
            filters.append(search_filter)

        if category is not None:
            filters.append(InventoryItem.category == category)

        count_stmt = select(func.count(InventoryItem.id)).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = select(InventoryItem).where(*filters)
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
        filters = []
        if item_id is not None:
            filters.append(InventoryMovement.item_id == item_id)
        if movement_type is not None:
            filters.append(InventoryMovement.movement_type == movement_type)

        count_stmt = select(func.count(InventoryMovement.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = select(InventoryMovement)
        if filters:
            stmt = stmt.where(*filters)

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
        count_stmt = select(func.count(RequisitionOrder.id))
        if status is not None:
            count_stmt = count_stmt.where(RequisitionOrder.status == status)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = select(RequisitionOrder)
        if status is not None:
            stmt = stmt.where(RequisitionOrder.status == status)

        valid_fields = {"created_at", "status", "quantity", "updated_at"}
        stmt = apply_sorting(stmt, sort, valid_fields)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def soft_delete_item(self, item_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime

        stmt = select(InventoryItem).where(
            InventoryItem.id == item_id, InventoryItem.deleted_at.is_(None)
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
        stmt = select(InventoryItem).where(
            InventoryItem.id.in_(ids), InventoryItem.deleted_at.is_(None)
        )
        items = (await self._session.execute(stmt)).scalars().all()
        for item in items:
            item.deleted_at = now
        await self._session.flush()
        return len(items)

    # ── Supplier CRUD ─────────────────────────────────────────────────

    SEARCH_FIELDS_SUPPLIERS = ("name", "contact_person", "email", "phone", "gst_number")
    SORTABLE_FIELDS_SUPPLIERS = {"name", "contact_person", "email", "is_active", "created_at"}

    async def create_supplier(self, supplier: Supplier) -> Supplier:
        self._session.add(supplier)
        await self._session.flush()
        return supplier

    async def get_supplier_by_id(self, supplier_id: uuid.UUID) -> Supplier | None:
        stmt = select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_supplier_by_name(self, name: str) -> Supplier | None:
        stmt = select(Supplier).where(
            Supplier.name == name,
            Supplier.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_suppliers_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[Sequence[Supplier], int]:
        stmt = select(Supplier).where(Supplier.deleted_at.is_(None))
        search_filter = build_search_filter(Supplier, search_term, self.SEARCH_FIELDS_SUPPLIERS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        if is_active is not None:
            stmt = stmt.where(Supplier.is_active == is_active)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS_SUPPLIERS)
        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()
        return results, total

    async def update_supplier(self, supplier: Supplier, **kwargs: object) -> Supplier:
        for key, value in kwargs.items():
            if hasattr(supplier, key):
                setattr(supplier, key, value)
        await self._session.flush()
        await self._session.refresh(supplier)
        return supplier

    async def soft_delete_supplier(self, supplier_id: uuid.UUID) -> bool:
        from datetime import UTC, datetime

        stmt = select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.deleted_at.is_(None),
        )
        supplier = (await self._session.execute(stmt)).scalar_one_or_none()
        if supplier is None:
            return False
        supplier.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def create_item_supplier(self, link: InventoryItemSupplier) -> InventoryItemSupplier:
        self._session.add(link)
        await self._session.flush()
        return link

    async def get_item_suppliers(self, item_id: uuid.UUID) -> Sequence[InventoryItemSupplier]:
        stmt = (
            select(InventoryItemSupplier)
            .where(InventoryItemSupplier.item_id == item_id)
            .order_by(InventoryItemSupplier.is_preferred.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_supplier_items(self, supplier_id: uuid.UUID) -> Sequence[InventoryItemSupplier]:
        stmt = select(InventoryItemSupplier).where(InventoryItemSupplier.supplier_id == supplier_id)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_item_supplier(
        self, item_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> InventoryItemSupplier | None:
        stmt = select(InventoryItemSupplier).where(
            InventoryItemSupplier.item_id == item_id,
            InventoryItemSupplier.supplier_id == supplier_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_item_supplier_links(
        self, item_id: uuid.UUID
    ) -> Sequence[tuple[InventoryItemSupplier, str]]:
        stmt = (
            select(InventoryItemSupplier, Supplier.name)
            .join(Supplier, Supplier.id == InventoryItemSupplier.supplier_id)
            .where(InventoryItemSupplier.item_id == item_id, Supplier.deleted_at.is_(None))
            .order_by(InventoryItemSupplier.is_preferred.desc(), Supplier.name.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [(link, name) for link, name in rows]

    async def clear_preferred_supplier(self, item_id: uuid.UUID) -> None:
        stmt = (
            update(InventoryItemSupplier)
            .where(InventoryItemSupplier.item_id == item_id, InventoryItemSupplier.is_preferred)
            .values(is_preferred=False)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def delete_item_supplier(self, item_id: uuid.UUID, supplier_id: uuid.UUID) -> bool:
        stmt = delete(InventoryItemSupplier).where(
            InventoryItemSupplier.item_id == item_id,
            InventoryItemSupplier.supplier_id == supplier_id,
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return bool(result.rowcount)  # type: ignore[attr-defined]
