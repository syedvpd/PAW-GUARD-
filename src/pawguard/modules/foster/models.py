"""ORM models for the Foster Management module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.auth.models import User
    from pawguard.modules.dog.models import DogProfile


class FosterStatus(StrEnum):
    APPLIED = "applied"
    APPROVED = "approved"
    REJECTED = "rejected"
    INACTIVE = "inactive"


class FosterProfile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "foster_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[FosterStatus] = mapped_column(
        String(32), default=FosterStatus.APPLIED, nullable=False, index=True
    )

    # e.g., "Pups, Medical Recovery, Behavior Modification"
    preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="joined")
    placements: Mapped[list["FosterPlacement"]] = relationship(
        back_populates="foster", cascade="all, delete-orphan"
    )


class FosterPlacement(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "foster_placements"

    foster_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("foster_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dog_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    foster: Mapped["FosterProfile"] = relationship(back_populates="placements")
    dog: Mapped["DogProfile"] = relationship("DogProfile", lazy="joined")
    progress_logs: Mapped[list["FosterProgressLog"]] = relationship(
        back_populates="placement", cascade="all, delete-orphan"
    )
    supply_dispatches: Mapped[list["FosterSupplyDispatch"]] = relationship(
        back_populates="placement", cascade="all, delete-orphan"
    )


class SupplyItemType(StrEnum):
    FOOD = "food"
    CRATE = "crate"
    MEDICATION = "medication"
    BEDDING = "bedding"
    TOYS = "toys"
    OTHER = "other"


class FosterSupplyDispatch(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "foster_supply_dispatches"

    placement_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("foster_placements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dispatched_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    item_type: Mapped[SupplyItemType] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    placement: Mapped["FosterPlacement"] = relationship(back_populates="supply_dispatches")


class FosterProgressLog(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "foster_progress_logs"

    placement_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("foster_placements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tracked_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    behavior_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    feeding_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    medication_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    exercise_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    mood_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    placement: Mapped["FosterPlacement"] = relationship(back_populates="progress_logs")
