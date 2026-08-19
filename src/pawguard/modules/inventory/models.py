"""ORM models for the Inventory, Pharmacy & Supply Chain module."""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class ItemCategory(StrEnum):
    PHARMACEUTICAL = "pharmaceutical"
    VACCINE = "vaccine"
    FOOD = "food"
    CONSUMABLE = "consumable"
    GEAR = "gear"
    OFFICE = "office"


class MovementType(StrEnum):
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    CONSUMPTION = "consumption"
    ADJUSTMENT = "adjustment"


class RequisitionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECEIVED = "received"


class InventoryItem(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "inventory_items"

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_items_quantity_non_negative"),
        CheckConstraint("unit_cost >= 0", name="ck_inventory_items_unit_cost_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    category: Mapped[ItemCategory] = mapped_column(String(64), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), default=0.0, nullable=False,
    )
    unit: Mapped[str] = mapped_column(String(32), nullable=False)  # vial, kg, pack, etc.
    reorder_threshold: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), default=10.0, nullable=False,
    )
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    unit_cost: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), default=0.0, nullable=False,
    )


class InventoryMovement(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "inventory_movements"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    moved_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    movement_type: Mapped[MovementType] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class RequisitionOrder(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "requisition_orders"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ,
        index=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=False)
    status: Mapped[RequisitionStatus] = mapped_column(
        String(32), default=RequisitionStatus.PENDING, nullable=False, index=True
    )


class Supplier(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InventoryItemSupplier(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "inventory_item_suppliers"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    unit_cost: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=False,
    )
    lead_time_days: Mapped[int | None] = mapped_column(nullable=True)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
