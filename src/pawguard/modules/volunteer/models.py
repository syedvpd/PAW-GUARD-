"""ORM models for the Volunteer Management module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.auth.models import User


class VolunteerStatus(StrEnum):
    APPLIED = "applied"
    ONBOARDED = "onboarded"
    ACTIVE = "active"
    INACTIVE = "inactive"


class VolunteerProfile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "volunteer_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[VolunteerStatus] = mapped_column(
        String(32), default=VolunteerStatus.APPLIED, nullable=False, index=True
    )

    emergency_contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    emergency_contact_phone: Mapped[str] = mapped_column(String(32), nullable=False)

    skills: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma separated e.g. "Grooming,Transport"
    availability: Mapped[str | None] = mapped_column(String(255), nullable=True)  # "Weekends", "Evenings", etc.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", lazy="joined")
    attendances: Mapped[list["ShiftAttendance"]] = relationship(
        back_populates="volunteer", cascade="all, delete-orphan"
    )


class VolunteerShift(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "volunteer_shifts"

    shelter_facility_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)  # Feeding, Cleaning, Walking, Admin
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    attendances: Mapped[list["ShiftAttendance"]] = relationship(
        back_populates="shift", cascade="all, delete-orphan"
    )


class ShiftAttendance(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "shift_attendances"

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("volunteer_shifts.id", ondelete="CASCADE"), nullable=False
    )
    volunteer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("volunteer_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hours_logged: Mapped[float | None] = mapped_column(nullable=True)

    volunteer: Mapped["VolunteerProfile"] = relationship(back_populates="attendances")
    shift: Mapped["VolunteerShift"] = relationship(back_populates="attendances")
