"""ORM models for the Vehicle Fleet & Equipment Management module."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class VehicleStatus(StrEnum):
    ACTIVE = "active"
    IN_MAINTENANCE = "in_maintenance"
    OUT_OF_SERVICE = "out_of_service"


class VehicleType(StrEnum):
    RESCUE_VAN = "rescue_van"
    AMBULANCE = "ambulance"
    MOBILE_VET_UNIT = "mobile_vet_unit"
    UTILITY = "utility"
    OTHER = "other"


class MaintenanceType(StrEnum):
    SERVICE = "service"
    SAFETY_INSPECTION = "safety_inspection"
    REPAIR = "repair"


class EquipmentCategory(StrEnum):
    NET_GUN = "net_gun"
    TRAP = "trap"
    TEMPERATURE_CONTROLLED_CAGE = "temperature_controlled_cage"
    MICROCHIP_READER = "microchip_reader"
    OTHER = "other"


class EquipmentCondition(StrEnum):
    GOOD = "good"
    NEEDS_REPAIR = "needs_repair"
    RETIRED = "retired"


class Vehicle(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "vehicles"

    make_model: Mapped[str] = mapped_column(String(255), nullable=False)
    license_plate: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    vehicle_type: Mapped[VehicleType | None] = mapped_column(
        String(32), default=VehicleType.RESCUE_VAN, nullable=True, index=True
    )
    status: Mapped[VehicleStatus] = mapped_column(
        String(32), default=VehicleStatus.ACTIVE, nullable=False
    )
    mileage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    primary_driver_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    insurance_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insurance_policy_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    insurance_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    insurance_contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)


class FleetMaintenance(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "fleet_maintenances"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    maintenance_type: Mapped[str] = mapped_column(
        String(32), default=MaintenanceType.SERVICE, server_default="service", nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class EquipmentAsset(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """High-value capture equipment register (PRR 3.13)."""

    __tablename__ = "equipment_assets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(
        String(64), default=EquipmentCategory.OTHER, nullable=False
    )
    serial_number: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    condition: Mapped[str] = mapped_column(
        String(32), default=EquipmentCondition.GOOD, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EquipmentCheckout(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "equipment_checkouts"
    __table_args__ = (
        Index(
            "uq_equipment_checkouts_asset_outstanding",
            "asset_id",
            unique=True,
            postgresql_where=text("asset_id IS NOT NULL AND returned_at IS NULL"),
            sqlite_where=text("asset_id IS NOT NULL AND returned_at IS NULL"),
        ),
    )

    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("equipment_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Net Gun, Trap, Crate, etc.
    equipment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_to_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_to_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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
    # When the equipment is expected to come back (PRR 3.13): checkout creation
    # enforces a value (explicit or a default window) and the return flow flags
    # late returns in the notes. NULL backfills keep pre-existing rows valid.
    expected_return_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FuelLog(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "fuel_logs"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fuel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    volume_litres: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    mileage_at_fill: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BreakdownSeverity(StrEnum):
    MINOR = "minor"
    MODERATE = "moderate"
    CRITICAL = "critical"


class BreakdownStatus(StrEnum):
    REPORTED = "reported"
    IN_REPAIR = "in_repair"
    RESOLVED = "resolved"


class FleetBreakdownReport(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "fleet_breakdown_reports"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    breakdown_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(32), default=BreakdownSeverity.MODERATE, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=BreakdownStatus.REPORTED, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
