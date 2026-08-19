"""ORM models for the Donation Management module."""

import uuid
from datetime import date as date_type
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from pawguard.modules.auth.models import User
    from pawguard.modules.dog.models import DogProfile


class DonationType(StrEnum):
    ONE_TIME = "one_time"
    RECURRING = "recurring"
    SPONSORSHIP = "sponsorship"


class DonationStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class RecurringFrequency(StrEnum):
    MONTHLY = "monthly"


class RecurringStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class SponsorshipStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class CampaignType(StrEnum):
    EMERGENCY = "emergency"
    RESCUE = "rescue"
    OPERATIONS = "operations"
    GENERAL = "general"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DonorProfile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "donor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    tax_identifier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    full_name_for_80g: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_for_80g: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_80g_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="joined")
    donations: Mapped[list["Donation"]] = relationship(
        back_populates="donor", cascade="all, delete-orphan"
    )


class DogSponsorship(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "dog_sponsorships"

    __table_args__ = (
        CheckConstraint("monthly_amount > 0", name="ck_dog_sponsorships_monthly_amount_positive"),
    )

    donor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("donor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dog_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dog_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monthly_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[SponsorshipStatus] = mapped_column(
        String(32), default=SponsorshipStatus.ACTIVE, nullable=False, index=True
    )
    next_charge_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    donor: Mapped["DonorProfile"] = relationship("DonorProfile", lazy="joined")
    dog: Mapped["DogProfile"] = relationship("DogProfile", lazy="joined")


class RecurringSubscription(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    """A monthly recurring donation linked to a donor profile (audit 3.11).

    Each due charge is recorded as a PENDING `Donation` (donation_type=RECURRING,
    recurring_subscription_id set) and confirmed via the existing order/verify/
    webhook flow. The next_charge_date advances one month once payment succeeds.
    """

    __tablename__ = "recurring_subscriptions"

    donor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("donor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    frequency: Mapped[RecurringFrequency] = mapped_column(
        String(32), default=RecurringFrequency.MONTHLY, nullable=False
    )
    status: Mapped[RecurringStatus] = mapped_column(
        String(32), default=RecurringStatus.ACTIVE, nullable=False, index=True
    )
    next_charge_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    donor: Mapped["DonorProfile"] = relationship("DonorProfile", lazy="joined")
    donations: Mapped[list["Donation"]] = relationship(
        back_populates="recurring_subscription", lazy="selectin"
    )


class Donation(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "donations"

    __table_args__ = (CheckConstraint("amount > 0", name="ck_donations_amount_positive"),)

    donor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("donor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dog_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dog_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sponsorship_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dog_sponsorships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recurring_subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("recurring_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("donation_campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    payment_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gateway_order_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gateway_signature: Mapped[str | None] = mapped_column(String(512), nullable=True)
    receipt_file_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    donor: Mapped["DonorProfile"] = relationship(back_populates="donations")
    dog: Mapped["DogProfile"] = relationship("DogProfile", lazy="joined")
    sponsorship: Mapped["DogSponsorship | None"] = relationship("DogSponsorship", lazy="joined")
    recurring_subscription: Mapped["RecurringSubscription | None"] = relationship(
        "RecurringSubscription", back_populates="donations", lazy="joined"
    )
    campaign: Mapped["DonationCampaign | None"] = relationship(
        back_populates="donations", lazy="joined"
    )


class DonationCampaign(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """A goal-oriented fundraising drive (PRR 3.1.7 / 3.11).

    Donations can be attributed to a campaign via `Donation.campaign_id`.
    A campaign automatically transitions to COMPLETED once its goal is
    reached or its end date passes.
    """

    __tablename__ = "donation_campaigns"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    campaign_type: Mapped[CampaignType] = mapped_column(
        String(32), default=CampaignType.GENERAL, nullable=False
    )
    status: Mapped[CampaignStatus] = mapped_column(
        String(32), default=CampaignStatus.DRAFT, nullable=False, index=True
    )
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    goal_reached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    donations: Mapped[list["Donation"]] = relationship(back_populates="campaign", lazy="selectin")
