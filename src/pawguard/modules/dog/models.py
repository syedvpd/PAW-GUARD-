"""ORM models for the Dog Management module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.companion_pet.models import SafetyTag



class DogStatus(StrEnum):
    RESCUED = "rescued"
    CLINIC = "clinic"
    SHELTER = "shelter"
    FOSTERED = "fostered"
    ADOPTED = "adopted"


class DogGender(StrEnum):
    """Controlled sex values (PRR 3.4 Demographics: Sex)."""

    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class DogTemperament(StrEnum):
    """Behavioral-matrix values (PRR 3.4): Friendly, Timid/Fearful, Aggressive,
    High Energy, Pack Compatible, Cat/Child Safe - plus unknown for intake.
    """

    FRIENDLY = "friendly"
    TIMID_FEARFUL = "timid_fearful"
    AGGRESSIVE = "aggressive"
    HIGH_ENERGY = "high_energy"
    PACK_COMPATIBLE = "pack_compatible"
    CAT_CHILD_SAFE = "cat_child_safe"
    UNKNOWN = "unknown"


class DogBreedClassification(StrEnum):
    """Breed classification (PRR 3.4 Demographics: Pure/Mix/Unknown)."""

    PURE = "pure"
    MIX = "mix"
    UNKNOWN = "unknown"


class DogEarShape(StrEnum):
    """Visual attribute: ear shape (PRR 3.4 Visual Attributes)."""

    PRICKED = "pricked"
    FLOPPY = "floppy"
    SEMI_PRICKED = "semi_pricked"
    ROSE = "rose"
    BUTTON = "button"
    UNKNOWN = "unknown"


class DogTailType(StrEnum):
    """Visual attribute: tail type (PRR 3.4 Visual Attributes)."""

    STRAIGHT = "straight"
    CURLED = "curled"
    DOCKED = "docked"
    LONG = "long"
    BOBTAIL = "bobtail"
    UNKNOWN = "unknown"


class DogActivityEventType(StrEnum):
    """Lifecycle events recorded in the dog's immutable activity stream (PRR 3.4)."""

    REGISTERED = "registered"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    DELETED = "deleted"
    WEIGHT_RECORDED = "weight_recorded"
    BULK_STATUS_UPDATED = "bulk_status_updated"
    BULK_DELETED = "bulk_deleted"


class DogProfile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "dog_profiles"

    __table_args__ = (
        Index("ix_dog_profiles_status_shelter_facility_id", "status", "shelter_facility_id"),
        Index("ix_dog_profiles_status_is_adoptable", "status", "is_adoptable"),
    )

    registration_number: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    rescue_case_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rescue_requests.id", ondelete="SET NULL"), nullable=True
    ,
        index=True
    )
    microchip_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    breed: Mapped[str] = mapped_column(String(128), default="indie_mix", nullable=False)
    breed_classification: Mapped[DogBreedClassification] = mapped_column(
        String(16), default=DogBreedClassification.UNKNOWN, nullable=False
    )
    gender: Mapped[DogGender] = mapped_column(
        String(16), default=DogGender.UNKNOWN, nullable=False, index=True
    )
    is_spayed_neutered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    estimated_age: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g., "2 years"
    # Numeric age in months for range filtering on the public adoption
    # directory (PRR 3.1.4: age filter). Derived from estimated_age at
    # write time when not supplied explicitly; NULL when unparseable.
    age_months: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    weight: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # in kg
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperament: Mapped[DogTemperament | None] = mapped_column(
        String(64), nullable=True
    )

    # Visual attributes (PRR 3.4): primary identification markers, ear shape,
    # tail type help adopters recognize a dog from its gallery photos.
    ear_shape: Mapped[DogEarShape | None] = mapped_column(String(32), nullable=True)
    tail_type: Mapped[DogTailType | None] = mapped_column(String(32), nullable=True)
    distinctive_markers: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # e.g., "white patch on chest, notched left ear"

    # Public gallery URLs for the adoption directory. Seeded directly with
    # external CDN URLs so the listing endpoint can render images without
    # requiring every dog to also have a StoredFile row in the storage module.
    image_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[DogStatus] = mapped_column(
        String(32), default=DogStatus.RESCUED, nullable=False, index=True
    )
    shelter_facility_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("shelter_facilities.id", ondelete="SET NULL"),
        nullable=True,
    
        index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("shelter_sections.id", ondelete="SET NULL"),
        nullable=True,
    
        index=True
    )
    kennel_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("kennels.id", ondelete="SET NULL"),
        nullable=True,
    
        index=True
    )
    foster_home_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("foster_profiles.id", ondelete="SET NULL"),
        nullable=True,
    
        index=True
    )

    is_adoptable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_quarantine_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    safety_tags: Mapped[list["SafetyTag"]] = relationship("SafetyTag", back_populates="dog", cascade="all, delete-orphan")



class DogWeightLog(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """Weight measurement history for a dog (PRR 3.4 Demographics: Weight History).

    The profile's ``weight`` column holds the current weight; every measurement
    appends an immutable row here so trends can be tracked over time.
    """

    __tablename__ = "dog_weight_logs"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dog_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    measured_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    ,
        index=True
    )
    weight: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # in kg
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DogActivityLog(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """Immutable chronological activity stream for a dog's master profile.

    PRR 3.4: the dog profile "maintains a permanent, audit-ready digital trail
    from initial intake through final resolution" - every lifecycle event
    (registration, status change, update, deletion, bulk operations) appends a
    row here. Rows are never updated or deleted; the stream is append-only.
    """

    __tablename__ = "dog_activity_logs"

    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dog_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[DogActivityEventType] = mapped_column(
        String(64), nullable=False, index=True
    )
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
