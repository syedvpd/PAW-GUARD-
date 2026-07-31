"""ORM models for the Shelter & Capacity Management module."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class FacilityStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class FacilityType(StrEnum):
    SHELTER = "shelter"
    CLINIC = "clinic"
    FOSTER_HOME = "foster_home"
    PARTNER = "partner"


class KennelSanitationState(StrEnum):
    CLEAN = "clean"
    NEEDS_CLEANING = "needs_cleaning"
    DISINFECTING = "disinfecting"
    OUT_OF_SERVICE = "out_of_service"


class TransferStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ShelterFacility(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "shelter_facilities"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    total_capacity: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    status: Mapped[FacilityStatus] = mapped_column(
        String(32), default=FacilityStatus.ACTIVE, nullable=False, index=True
    )
    facility_type: Mapped[FacilityType] = mapped_column(
        String(32), default=FacilityType.SHELTER, nullable=False, index=True
    )


class ShelterSection(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "shelter_sections"

    facility_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("shelter_facilities.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # Quarantine, Isolation, general, etc.
    capacity: Mapped[int] = mapped_column(Integer, default=10, nullable=False)


class Kennel(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "kennels"

    section_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shelter_sections.id", ondelete="CASCADE"), nullable=False
    )
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., K-08
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sanitation_state: Mapped[KennelSanitationState] = mapped_column(
        String(32), default=KennelSanitationState.CLEAN, nullable=False
    )


class FacilityTransfer(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "facility_transfers"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    )
    from_facility_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("shelter_facilities.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_facility_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("shelter_facilities.id", ondelete="CASCADE"),
        nullable=False,
    )
    transferred_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[TransferStatus] = mapped_column(
        String(32), default=TransferStatus.PENDING, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Dual confirmation: a transfer only completes once both the sending and
    # the receiving facility have separately confirmed it (PRR 3.6).
    sender_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sender_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    receiver_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    receiver_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class DailyCareLog(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "daily_care_logs"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    )
    logged_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    feed_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dietary_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    exercise_hours: Mapped[float] = mapped_column(Numeric(4, 2), default=0.0, nullable=False)
    behavioral_enrichment: Mapped[str | None] = mapped_column(Text, nullable=True)
