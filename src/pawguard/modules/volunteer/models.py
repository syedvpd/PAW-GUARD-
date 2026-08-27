"""ORM models for the Volunteer Management module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.auth.models import User


class VolunteerStatus(StrEnum):
    APPLIED = "applied"
    PENDING = "pending"
    APPROVED = "approved"
    ONBOARDED = "onboarded"
    ACTIVE = "active"
    INACTIVE = "inactive"
    REJECTED = "rejected"


class ApplicationStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class AttendanceStatus(StrEnum):
    """Lifecycle of a single shift claim, per the documented workflow:

    CLAIMED -> CHECKED_IN -> CHECKED_OUT
    CLAIMED -> NO_SHOW  (coordinator-marked only, never inferred)
    CLAIMED -> CANCELLED
    """

    CLAIMED = "claimed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class VolunteerApplication(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """Tracks volunteer applications through the approval workflow."""

    __tablename__ = "volunteer_applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        String(32), default=ApplicationStatus.SUBMITTED, nullable=False, index=True
    )
    emergency_contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    emergency_contact_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    animal_handling_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="joined")


class VolunteerProfile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "volunteer_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("volunteer_applications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[VolunteerStatus] = mapped_column(
        String(32), default=VolunteerStatus.APPLIED, nullable=False, index=True
    )

    emergency_contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    emergency_contact_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_role: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # comma separated e.g. "Grooming,Transport,Photography,Training"
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # "Weekends", "Evenings", etc.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Onboarding/skills matrix (PRR 3.9) - previously absent from the model.
    background_check_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    background_check_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    animal_handling_experience: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="joined")
    attendances: Mapped[list["ShiftAttendance"]] = relationship(
        back_populates="volunteer", cascade="all, delete-orphan"
    )


class VolunteerShift(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "volunteer_shifts"

    shelter_facility_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    # Feeding, Cleaning, Walking, Admin
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    allowed_radius_meters: Mapped[int | None] = mapped_column(Integer, default=500, nullable=True)

    attendances: Mapped[list["ShiftAttendance"]] = relationship(
        back_populates="shift", cascade="all, delete-orphan"
    )


class ShiftAttendance(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "shift_attendances"

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("volunteer_shifts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    volunteer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("volunteer_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hours_logged: Mapped[float | None] = mapped_column(nullable=True)

    check_in_lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    check_in_lng: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    check_in_distance_meters: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    check_out_lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    check_out_lng: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    check_out_distance_meters: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    status: Mapped[AttendanceStatus] = mapped_column(
        String(32), default=AttendanceStatus.CLAIMED, nullable=False, index=True
    )
    no_show_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    no_show_marked_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    no_show_marked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Set once the shift-reminder job successfully notifies this volunteer;
    # the NULL check is the dedup key so a re-run of the job (retry, or the
    # next scheduled tick before the window rolls past this shift) never
    # sends a second reminder for the same claimed attendance.
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    volunteer: Mapped["VolunteerProfile"] = relationship(back_populates="attendances")
    shift: Mapped["VolunteerShift"] = relationship(back_populates="attendances")
