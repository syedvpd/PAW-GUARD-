"""ORM models for the Adoption Management module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.auth.models import User
    from pawguard.modules.dog.models import DogProfile


class AdoptionStatus(StrEnum):
    SUBMITTED = "submitted"
    VETTING = "vetting"
    HOME_CHECK = "home_check"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class AdoptionApplication(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "adoption_applications"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="CASCADE"), nullable=False
    )
    adopter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[AdoptionStatus] = mapped_column(
        String(32), default=AdoptionStatus.SUBMITTED, nullable=False, index=True
    )

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
    adoption_agreement_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dog: Mapped["DogProfile"] = relationship("DogProfile", lazy="joined")
    adopter: Mapped["User"] = relationship("User", lazy="joined")
    scores: Mapped[list["AdoptionScore"]] = relationship(
        "AdoptionScore", back_populates="application", lazy="selectin"
    )


class AdoptionScore(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "adoption_scores"

    application_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("adoption_applications.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    scored_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
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
