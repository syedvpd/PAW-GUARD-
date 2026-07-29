"""ORM models for the Emergency Rescue module."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class RescueStatus(StrEnum):
    REPORTED = "reported"
    VERIFIED = "verified"
    DISPATCHED = "dispatched"
    LOCATED = "located"
    RESCUED = "rescued"
    ADMITTED = "admitted"
    REJECTED = "rejected"


class RescueRequest(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "rescue_requests"

    ticket_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    reporter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reporter_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    reporter_alternate_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reporter_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    location_address: Mapped[str] = mapped_column(Text, nullable=False)
    location_landmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    animal_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    physical_condition: Mapped[str] = mapped_column(String(64), nullable=False)  # Critical, Injured, Sick, Malnourished, Stray
    behavioral_indicators: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[RescueStatus] = mapped_column(
        String(32), default=RescueStatus.REPORTED, nullable=False, index=True
    )
    rejection_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    dispatch: Mapped["RescueDispatch | None"] = relationship(
        back_populates="rescue_request", uselist=False, cascade="all, delete-orphan"
    )
    reports: Mapped[list["RescueReport"]] = relationship(
        back_populates="rescue_request", cascade="all, delete-orphan"
    )


class RescueDispatch(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "rescue_dispatches"

    rescue_request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rescue_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    assigned_driver_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    vehicle_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    equipment_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    located_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rescued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Fled, Inaccessible, False Report, etc.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rescue_request: Mapped["RescueRequest"] = relationship(back_populates="dispatch")


class RescueReport(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "rescue_reports"

    rescue_request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rescue_requests.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)  # Store up to 5 URLs

    rescue_request: Mapped["RescueRequest"] = relationship(back_populates="reports")
