"""ORM models for the Foster Management module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.auth.models import User
    from pawguard.modules.dog.models import DogProfile


class FosterStatus(StrEnum):
    APPLIED = "applied"
    APPROVED = "approved"
    REJECTED = "rejected"
    INACTIVE = "inactive"


class FosterProfile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
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

    user: Mapped["User"] = relationship("User", lazy="joined")
    placements: Mapped[list["FosterPlacement"]] = relationship(
        back_populates="foster", cascade="all, delete-orphan"
    )


class FosterPlacement(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "foster_placements"

    foster_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("foster_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    )

    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    foster: Mapped["FosterProfile"] = relationship(back_populates="placements")
    dog: Mapped["DogProfile"] = relationship("DogProfile", lazy="joined")
