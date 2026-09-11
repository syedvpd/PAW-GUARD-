"""Database models for Invoicing & Service Fee Collection."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class InvoiceType(StrEnum):
    PARTNER_BILLING = "partner_billing"  # billing an org with no app (shelter, clinic, sponsor)
    SERVICE_FEE = "service_fee"  # platform's cut of an in-product transaction


class InvoiceStatus(StrEnum):
    DRAFT = "draft"  # created, link not yet issued
    SENT = "sent"  # payment link created & delivered
    PAID = "paid"  # gateway confirmed payment
    OVERDUE = "overdue"  # past due_date, still unpaid
    CANCELLED = "cancelled"  # voided before payment
    FAILED = "failed"  # link expired or payment attempt failed


class Invoice(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "invoices"

    invoice_number: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )  # e.g. INV-2026-0001
    invoice_type: Mapped[InvoiceType] = mapped_column(
        SAEnum(InvoiceType, values_callable=lambda e: [i.value for i in e], native_enum=False),
        nullable=False,
        index=True,
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, values_callable=lambda e: [i.value for i in e], native_enum=False),
        default=InvoiceStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # Who's being billed — at least one of these two must be set
    billed_org_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billed_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Linkage back to what generated this invoice
    source_module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_reference_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # Gateway state
    payment_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)  # "razorpay"
    payment_link_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payment_link_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    billed_user = relationship("User", foreign_keys=[billed_user_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
