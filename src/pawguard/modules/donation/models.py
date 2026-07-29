"""ORM models for the Donation Management module."""

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class DonationType(StrEnum):
    ONE_TIME = "one_time"
    RECURRING = "recurring"
    SPONSORSHIP = "sponsorship"


class DonationStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class DonorProfile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "donor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    tax_identifier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", lazy="joined")
    donations: Mapped[list["Donation"]] = relationship(
        back_populates="donor", cascade="all, delete-orphan"
    )


class Donation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "donations"

    donor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("donor_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    dog_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="SET NULL"), nullable=True
    )

    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    donation_type: Mapped[DonationType] = mapped_column(
        String(32), default=DonationType.ONE_TIME, nullable=False
    )
    status: Mapped[DonationStatus] = mapped_column(
        String(32), default=DonationStatus.PENDING, nullable=False, index=True
    )
    transaction_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    donor: Mapped["DonorProfile"] = relationship(back_populates="donations")
    dog: Mapped["DogProfile"] = relationship("DogProfile", lazy="joined")
