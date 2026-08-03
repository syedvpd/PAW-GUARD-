"""ORM models for the Lost & Found module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.auth.models import User


class Species(StrEnum):
    DOG = "dog"
    CAT = "cat"
    BIRD = "bird"
    RABBIT = "rabbit"
    OTHER = "other"


class ReportStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class MatchStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class LostReport(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "lost_reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    species: Mapped[Species] = mapped_column(
        String(32), default=Species.DOG, nullable=False, index=True
    )
    pet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    breed: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str] = mapped_column(String(64), nullable=False)
    microchip_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collar_color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collar_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    marker_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    location_address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    lost_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        String(32), default=ReportStatus.ACTIVE, nullable=False, index=True
    )
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped["User"] = relationship("User", lazy="joined")


class FoundReport(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "found_reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    species: Mapped[Species] = mapped_column(
        String(32), default=Species.DOG, nullable=False, index=True
    )
    breed_observed: Mapped[str] = mapped_column(String(128), nullable=False)
    color_observed: Mapped[str] = mapped_column(String(64), nullable=False)
    collar_color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collar_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    marker_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    location_address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        String(32), default=ReportStatus.ACTIVE, nullable=False, index=True
    )
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped["User"] = relationship("User", lazy="joined")


class ReportMatch(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "report_matches"

    lost_report_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("lost_reports.id", ondelete="CASCADE"), nullable=False
    )
    found_report_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("found_reports.id", ondelete="CASCADE"), nullable=False
    )

    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0, nullable=False)
    status: Mapped[MatchStatus] = mapped_column(
        String(32), default=MatchStatus.PENDING, nullable=False, index=True
    )
    # Score-basis transparency (PRR 3.10): computed by the matcher at match time
    # and persisted so the API response can show *why* a match was made.
    distance_km: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    temporal_gap_days: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    match_reasons: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    microchip_doc_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    vet_bill_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    photo_proof_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claim_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claim_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    lost_report: Mapped["LostReport"] = relationship("LostReport", lazy="joined")
    found_report: Mapped["FoundReport"] = relationship("FoundReport", lazy="joined")
