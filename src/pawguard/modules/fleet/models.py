"""ORM models for the Vehicle Fleet & Equipment Management module."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class VehicleStatus(StrEnum):
    ACTIVE = "active"
    IN_MAINTENANCE = "in_maintenance"
    OUT_OF_SERVICE = "out_of_service"


class Vehicle(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "vehicles"

    make_model: Mapped[str] = mapped_column(String(255), nullable=False)
    license_plate: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[VehicleStatus] = mapped_column(
        String(32), default=VehicleStatus.ACTIVE, nullable=False
    )
    mileage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    primary_driver_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    insurance_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insurance_policy_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    insurance_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    insurance_contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)


class FleetMaintenance(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "fleet_maintenances"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class EquipmentCheckout(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "equipment_checkouts"

    # Net Gun, Trap, Crate, etc.
    equipment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_to_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_to_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    # Populated when the checkout was auto-created for a rescue dispatch
    # (PRR 3.3): links the equipment to the dispatch and lets the fleet module
    # release it automatically when the dispatch completes.
    rescue_dispatch_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rescue_dispatches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    checked_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FuelLog(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "fuel_logs"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    filled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    fuel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    volume_litres: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    mileage_at_fill: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
