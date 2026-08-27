"""ORM models for the Adoption Management module."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.auth.models import User
    from pawguard.modules.dog.models import DogProfile


class AdoptionStatus(StrEnum):
    """Six-phase adoption pipeline (PRR 3.7) plus a terminal REJECTED.

    SUBMITTED -> SCREENING -> INTERVIEW -> HOME_CHECK -> APPROVED -> COMPLETED.

    ``VETTING`` is a deprecated legacy member kept only so historical rows
    that stored the collapsed ``"vetting"`` value (the old phases 1+2) still
    parse. It is NOT part of the active state machine and has no valid
    transitions; new applications use SCREENING/INTERVIEW.
    """

    SUBMITTED = "submitted"
    SCREENING = "screening"
    INTERVIEW = "interview"
    HOME_CHECK = "home_check"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"
    VETTING = "vetting"  # deprecated legacy value, kept for data compatibility


class FollowUpStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    OVERDUE = "overdue"


class AdoptionApplication(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "adoption_applications"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dog_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    adopter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[AdoptionStatus] = mapped_column(
        String(32), default=AdoptionStatus.SUBMITTED, nullable=False, index=True
    )

    version_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    residential_status: Mapped[str] = mapped_column(String(32), nullable=False)  # owned, rented
    has_landlord_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_yard_fence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    household_members_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    existing_pets_medical_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    pet_care_experience: Mapped[str | None] = mapped_column(Text, nullable=True)

    vetting_officer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    home_inspection_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    home_inspection_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    home_inspection_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # "physical" | "virtual"
    interview_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    interview_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    interview_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    adoption_agreement_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fee_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=True
    )

    dog: Mapped["DogProfile"] = relationship("DogProfile", lazy="joined")
    adopter: Mapped["User"] = relationship("User", foreign_keys=[adopter_id], lazy="joined")
    scores: Mapped[list["AdoptionScore"]] = relationship(
        "AdoptionScore", back_populates="application", lazy="selectin"
    )
    follow_ups: Mapped[list["AdoptionFollowUp"]] = relationship(
        "AdoptionFollowUp", back_populates="application", lazy="selectin"
    )


class AdoptionScore(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "adoption_scores"

    application_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("adoption_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scored_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    home_environment_score: Mapped[int] = mapped_column(Integer, nullable=False)
    pet_care_knowledge_score: Mapped[int] = mapped_column(Integer, nullable=False)
    financial_readiness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    lifestyle_compatibility_score: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    application: Mapped["AdoptionApplication"] = relationship(
        "AdoptionApplication", back_populates="scores"
    )

    if TYPE_CHECKING:
        scored_by: Mapped["User"] = relationship("User", lazy="joined")


class AdoptionFollowUp(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """A scheduled post-adoption check-in (30/90/180 days after completion).

    Created by the background job for completed adoptions; adopters submit
    proof media + notes, or the check-in goes OVERDUE once past ``due_at``.
    """

    __tablename__ = "adoption_follow_ups"

    adoption_application_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("adoption_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    due_day: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[FollowUpStatus] = mapped_column(
        String(16), default=FollowUpStatus.PENDING, nullable=False, index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    media_keys: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["AdoptionApplication"] = relationship(
        "AdoptionApplication", back_populates="follow_ups"
    )
