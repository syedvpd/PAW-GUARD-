"""ORM models for the Dog Management module."""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class DogStatus(StrEnum):
    RESCUED = "rescued"
    CLINIC = "clinic"
    SHELTER = "shelter"
    FOSTERED = "fostered"
    ADOPTED = "adopted"


class DogProfile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "dog_profiles"

    registration_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    rescue_case_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rescue_requests.id", ondelete="SET NULL"), nullable=True
    )
    microchip_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    breed: Mapped[str] = mapped_column(String(128), default="indie_mix", nullable=False)
    gender: Mapped[str] = mapped_column(String(16), nullable=False)  # male, female
    is_spayed_neutered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    estimated_age: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g., "2 years"
    weight: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # in kg
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperament: Mapped[str | None] = mapped_column(String(64), nullable=True)  # friendly, timid, aggressive, etc.

    status: Mapped[DogStatus] = mapped_column(
        String(32), default=DogStatus.RESCUED, nullable=False, index=True
    )
    shelter_facility_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shelter_facilities.id", ondelete="SET NULL"), nullable=True
    )
    kennel_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("kennels.id", ondelete="SET NULL"), nullable=True
    )

    is_adoptable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_quarantine_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
