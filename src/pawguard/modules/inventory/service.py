"""InventoryService: owns stock levels, movement logs, and requisition flows.

Adheres to RULE-003.
"""

import contextlib
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.logging import get_logger
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import AdoptionApplication
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.foster.models import FosterPlacement, FosterProfile
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
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.schemas import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemSupplierCreate,
    InventoryItemSupplierResponse,
    InventoryItemUpdate,
    InventoryMovementCreate,
    InventoryMovementResponse,
    InventorySummaryResponse,
    InventoryTransferCreate,
    InventoryTransferResponse,
    RequisitionOrderCreate,
    RequisitionOrderResponse,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)
from pawguard.modules.medical.models import MedicalTreatment, Prescription
from pawguard.modules.notifications.schemas import BroadcastCreate
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.rescue.models import RescueRequest
from pawguard.modules.shelter.models import DailyCareLog, ShelterFacility
from pawguard.services.audit_service import AuditService

logger = get_logger(__name__)

REFERENCE_TYPE_TABLE_MAP: dict[str, Any] = {
    "dog": DogProfile,
    "rescue": RescueRequest,
    "treatment": MedicalTreatment,
    "medical_treatment": MedicalTreatment,
    "requisition": RequisitionOrder,
    "prescription": Prescription,
    "shelter_facility": ShelterFacility,
    "daily_care_log": DailyCareLog,
    "foster": FosterProfile,
    "foster_supply": FosterPlacement,
    "foster_placement": FosterPlacement,
    "adoption": AdoptionApplication,
}

EXPIRY_WARNING_DAYS = 60

REQUISITION_TRANSITIONS: dict[RequisitionStatus, frozenset[RequisitionStatus]] = {
    RequisitionStatus.PENDING: frozenset({RequisitionStatus.APPROVED, RequisitionStatus.REJECTED}),
    RequisitionStatus.APPROVED: frozenset({RequisitionStatus.RECEIVED, RequisitionStatus.REJECTED}),
    RequisitionStatus.REJECTED: frozenset(),
    RequisitionStatus.RECEIVED: frozenset(),
}

_NON_NULLABLE_ITEM_FIELDS = (
    "name",
    "category",
    "quantity",
    "unit",
    "reorder_threshold",
    "unit_cost",
)


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
            with contextlib.suppress(Exception):
                await self._redis.delete(
                    "cache:dashboard:inventory",
                    "cache:dashboard:operations",
                )

    async def create_item(
        self,
        payload: InventoryItemCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> InventoryItem:
        await self._ensure_facility(payload.facility_id)
        existing = await self._repo.get_item_by_name(payload.name, payload.facility_id)
        if existing is not None:
            raise ConflictError(f"Inventory item '{payload.name}' already registered.")

        item = InventoryItem(
            name=payload.name,
            facility_id=payload.facility_id,
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

    async def _ensure_facility(self, facility_id: uuid.UUID | None) -> None:
        if facility_id is not None and not await self._repo.facility_exists(facility_id):
            raise NotFoundError("Shelter facility not found.")

    async def record_movement(
        self,
        user_id: uuid.UUID,
        payload: InventoryMovementCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> InventoryMovement:
        """Records an inventory stock movement.

        Architectural Note: Polymorphic reference validated at application transaction boundary;
        database-level FK is intentionally impossible without a multi-table redesign because
        `reference_type` dynamically routes to different domain tables (dog, treatment, shift, etc.).
        """
        if (payload.reference_id is None) != (payload.reference_type is None):
            raise ValidationFailedError(
                "Both reference_type and reference_id must be provided together or both omitted."
            )

        if payload.reference_type is not None and payload.reference_id is not None:
            model_cls = REFERENCE_TYPE_TABLE_MAP.get(payload.reference_type)
            if model_cls is None:
                raise ValidationFailedError(f"Invalid reference_type '{payload.reference_type}'.")
            ref_entity = await self._repo._session.get(model_cls, payload.reference_id)
            if ref_entity is None:
                raise ValidationFailedError(
                    f"Referenced {payload.reference_type} with ID '{payload.reference_id}' does not exist."
                )
            del_val = getattr(ref_entity, "deleted_at", None)
            if del_val is not None:
                raise ValidationFailedError(
                    f"Referenced {payload.reference_type} with ID '{payload.reference_id}' has been soft-deleted and cannot be referenced."
                )

        item = await self._repo.get_item_for_update(payload.item_id)
        if item is None:
            item = await self._repo.get_item(payload.item_id)
        if item is None:
            raise NotFoundError("Inventory item not found.")

        qty_change = payload.quantity
        was_insufficient = False
        from datetime import date

        if payload.movement_type in (MovementType.CHECK_OUT, MovementType.CONSUMPTION):
            # Expiry date enforcement (PRD 3.12)
            if item.expiry_date is not None and item.expiry_date < date.today():
                raise ConflictError(
                    f"Cannot check out expired inventory item '{item.name}'. "
                    f"Expired on: {item.expiry_date}"
                )
            if item.quantity < qty_change and not payload.emergency_override:
                raise ConflictError(
                    f"Insufficient stock for '{item.name}'. "
                    f"Available: {item.quantity} {item.unit}, "
                    f"Requested: {qty_change}"
                )
            was_insufficient = item.quantity < qty_change
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
                    "emergency_override": was_insufficient and payload.emergency_override,
                },
            )
        # Workflow 8: when stock falls to/below the reorder threshold, alert
        # inventory staff and administrators so a purchase requisition can be
        # raised (avoids silent stock-outs of medicine/food).
        if item.quantity <= item.reorder_threshold:
            await self._alert_low_stock(item)
        # Medical suite edge case: a welfare-critical treatment proceeded
        # despite insufficient stock (negative-stock override) — flag it for
        # Inventory Manager review rather than letting it pass silently.
        if was_insufficient and payload.emergency_override:
            await self._alert_emergency_override(item, movement, moved_by=user_id)
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
            logger.warning("Failed to send low-stock alert for item %s", item.id, exc_info=True)

    async def _alert_emergency_override(
        self, item: InventoryItem, movement: InventoryMovement, moved_by: uuid.UUID
    ) -> None:
        if self._notification_svc is None:
            return
        try:
            await self._notification_svc.broadcast(
                payload=BroadcastCreate(
                    title=f"Emergency stock override: {item.name}",
                    body=(
                        f"A welfare-critical check-out took '{item.name}' below tracked stock "
                        f"(now {item.quantity} {item.unit}). Note: {movement.notes or 'none provided'}. "
                        "Review and reconcile stock."
                    ),
                    notification_type="inventory_emergency_override",
                    action_url="/inventory",
                    target_roles=["inventory_manager", "rescue_centre_admin"],
                ),
                # Workflow 6 §14: this alert must also reach the requesting
                # vet directly, not just the inventory-side roles — they're
                # the one who needs to know their override went through (or
                # follow up if reconciliation later reverses it).
                user_ids=[moved_by],
                actor_id=moved_by,
            )
        except Exception:  # pragma: no cover - alerting must never break stock ops
            logger.warning(
                "Failed to send emergency-override alert for item %s", item.id, exc_info=True
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
        if payload.supplier_id is not None:
            supplier = await self._repo.get_supplier_by_id(payload.supplier_id)
            if supplier is None:
                raise NotFoundError("Supplier not found.")
            if not supplier.is_active:
                raise ConflictError(f"Supplier '{supplier.name}' is inactive.")

        req = RequisitionOrder(
            item_id=payload.item_id,
            requester_id=user_id,
            quantity=payload.quantity,
            supplier_id=payload.supplier_id,
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
        if status not in REQUISITION_TRANSITIONS[req.status]:
            raise ConflictError(
                f"Requisition cannot move from {req.status.value} to {status.value}."
            )

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
        update_data = payload.model_dump(exclude_unset=True)
        for field in _NON_NULLABLE_ITEM_FIELDS:
            if field in update_data and update_data[field] is None:
                update_data.pop(field)
        if update_data.get("facility_id") is not None:
            await self._ensure_facility(update_data["facility_id"])
        target_name = update_data.get("name", item.name)
        target_facility = update_data.get("facility_id", item.facility_id)
        if (target_name, target_facility) != (item.name, item.facility_id):
            existing = await self._repo.get_item_by_name(target_name, target_facility)
            if existing is not None and existing.id != item.id:
                raise ConflictError(f"Inventory item '{target_name}' already registered.")
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
                    "changes": {k: None if v is None else str(v) for k, v in update_data.items()},
                },
            )
        return updated

    async def get_items_by_ids(
        self, item_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, InventoryItem | None]:
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
        facility_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[InventoryItemResponse]:
        items, total = await self._repo.list_items_paginated(
            page_params,
            sort,
            search_term=search_term,
            category=category,
            facility_id=facility_id,
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
            page_params,
            sort,
            item_id=item_id,
            movement_type=movement_type,
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
            page_params,
            sort,
            status=status,
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
        user_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        reqs = []
        for req_id in dict.fromkeys(ids):
            req = await self._repo.get_requisition(req_id)
            if req is None:
                raise NotFoundError(f"Requisition order {req_id} not found.")
            if status not in REQUISITION_TRANSITIONS[req.status]:
                raise ConflictError(
                    f"Requisition {req_id} cannot move from {req.status.value} to {status.value}."
                )
            reqs.append(req)
        for req in reqs:
            await self.update_requisition_status(
                user_id, req.id, status, actor_id=actor_id, ip_address=ip_address
            )
        return len(reqs)

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
                raise ConflictError(f"Supplier '{update_data['name']}' already registered.")
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
            page_params,
            sort,
            search_term=search_term,
            is_active=is_active,
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

    # ── Stock summary ─────────────────────────────────────────────────

    async def get_summary(self, today: date | None = None) -> InventorySummaryResponse:
        today = today or date.today()
        total, value, avg_cost = await self._repo.stock_totals()
        out_of_stock = await self._repo.list_out_of_stock()
        low_stock = await self._repo.list_low_stock()
        expiring = await self._repo.list_expiring(today + timedelta(days=EXPIRY_WARNING_DAYS))

        def to_response(items: Sequence[InventoryItem]) -> list[InventoryItemResponse]:
            return [InventoryItemResponse.model_validate(i) for i in items]

        return InventorySummaryResponse(
            total_items=total,
            out_of_stock_count=len(out_of_stock),
            low_stock_count=len(low_stock),
            expiring_count=len(expiring),
            expired_count=sum(
                1 for i in expiring if i.expiry_date is not None and i.expiry_date < today
            ),
            total_stock_value=round(value, 2),
            average_unit_cost=round(avg_cost, 2),
            expiry_warning_days=EXPIRY_WARNING_DAYS,
            out_of_stock=to_response(out_of_stock),
            low_stock=to_response(low_stock),
            expiring=to_response(expiring),
        )

    # ── Item-vendor links ─────────────────────────────────────────────

    async def list_item_suppliers(self, item_id: uuid.UUID) -> list[InventoryItemSupplierResponse]:
        await self.get_item(item_id)
        return [
            InventoryItemSupplierResponse.model_validate(link).model_copy(
                update={"supplier_name": name}
            )
            for link, name in await self._repo.list_item_supplier_links(item_id)
        ]

    async def link_item_supplier(
        self,
        item_id: uuid.UUID,
        payload: InventoryItemSupplierCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> InventoryItemSupplierResponse:
        await self.get_item(item_id)
        supplier = await self.get_supplier(payload.supplier_id)
        link = await self._repo.get_item_supplier(item_id, payload.supplier_id)
        if payload.is_preferred:
            await self._repo.clear_preferred_supplier(item_id)
        if link is None:
            link = await self._repo.create_item_supplier(
                InventoryItemSupplier(
                    item_id=item_id,
                    supplier_id=payload.supplier_id,
                    unit_cost=payload.unit_cost,
                    lead_time_days=payload.lead_time_days,
                    is_preferred=payload.is_preferred,
                )
            )
        else:
            link.unit_cost = payload.unit_cost
            link.lead_time_days = payload.lead_time_days
            link.is_preferred = payload.is_preferred
            await self._repo._session.flush()
        await self._repo._session.refresh(link)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "item_id": str(item_id),
                    "supplier_id": str(payload.supplier_id),
                    "is_preferred": payload.is_preferred,
                },
            )
        return InventoryItemSupplierResponse.model_validate(link).model_copy(
            update={"supplier_name": supplier.name}
        )

    async def unlink_item_supplier(
        self,
        item_id: uuid.UUID,
        supplier_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        if not await self._repo.delete_item_supplier(item_id, supplier_id):
            raise NotFoundError("Vendor is not linked to this item.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_ITEM_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"item_id": str(item_id), "unlinked_supplier_id": str(supplier_id)},
            )

    # ── Inter-facility transfers ──────────────────────────────────────

    async def transfer_stock(
        self,
        user_id: uuid.UUID,
        payload: InventoryTransferCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> InventoryTransferResponse:
        source = await self._repo.get_item_for_update(payload.item_id)
        if source is None:
            raise NotFoundError("Inventory item not found.")
        if source.facility_id == payload.to_facility_id:
            raise ValidationFailedError("Source and destination facility must differ.")
        await self._ensure_facility(payload.to_facility_id)
        if source.quantity < payload.quantity:
            raise ConflictError(
                f"Insufficient stock for '{source.name}'. "
                f"Available: {source.quantity} {source.unit}, Requested: {payload.quantity}"
            )

        existing = await self._repo.get_item_by_name(source.name, payload.to_facility_id)
        if existing is None:
            destination = await self._repo.create_item(
                InventoryItem(
                    name=source.name,
                    facility_id=payload.to_facility_id,
                    category=source.category,
                    quantity=0.0,
                    unit=source.unit,
                    reorder_threshold=source.reorder_threshold,
                    expiry_date=source.expiry_date,
                    unit_cost=source.unit_cost,
                )
            )
        else:
            if existing.unit != source.unit:
                raise ConflictError(
                    f"'{source.name}' is tracked in {existing.unit} at the destination, "
                    f"not {source.unit}."
                )
            destination = await self._repo.get_item_for_update(existing.id) or existing

        transfer_id = uuid.uuid4()
        source.quantity -= payload.quantity
        destination.quantity += payload.quantity
        for item, movement_type in (
            (source, MovementType.CHECK_OUT),
            (destination, MovementType.CHECK_IN),
        ):
            await self._repo.create_movement(
                InventoryMovement(
                    item_id=item.id,
                    moved_by=user_id,
                    movement_type=movement_type,
                    quantity=payload.quantity,
                    notes=payload.notes,
                    reference_type="inventory_transfer",
                    reference_id=transfer_id,
                )
            )
        await self._repo._session.flush()
        await self._repo._session.refresh(source)
        await self._repo._session.refresh(destination)
        await self._invalidate_dashboard_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.INVENTORY_STOCK_ADJUSTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "transfer_id": str(transfer_id),
                    "source_item_id": str(source.id),
                    "destination_item_id": str(destination.id),
                    "quantity": payload.quantity,
                },
            )
        if source.quantity <= source.reorder_threshold:
            await self._alert_low_stock(source)
        return InventoryTransferResponse(
            transfer_id=transfer_id,
            source_item=InventoryItemResponse.model_validate(source),
            destination_item=InventoryItemResponse.model_validate(destination),
        )
