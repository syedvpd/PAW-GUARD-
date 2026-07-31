"""ORM models for the Inventory, Pharmacy & Supply Chain module."""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


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
    ADJUSTMENT = "adjustment"


class RequisitionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECEIVED = "received"


class InventoryItem(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "inventory_items"

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


class InventoryMovement(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "inventory_movements"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    )
    moved_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movement_type: Mapped[MovementType] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class RequisitionOrder(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "requisition_orders"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=False)
    status: Mapped[RequisitionStatus] = mapped_column(
        String(32), default=RequisitionStatus.PENDING, nullable=False, index=True
    )
