"""ORM models for the Complaints, Feedback & Service Assurance module."""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import TimestampMixin, UUIDPkMixin


class GrievanceStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    AWAITING_RESPONSE = "awaiting_response"
    RESOLVED = "resolved"
    CLOSED = "closed"


class GrievanceTicket(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "grievance_tickets"

    reporter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reporter_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    reporter_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    complaint_type: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[GrievanceStatus] = mapped_column(
        String(32), default=GrievanceStatus.OPEN, nullable=False, index=True
    )
    assigned_to_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class GrievanceComment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "grievance_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("grievance_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ServiceFeedback(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "service_feedbacks"

    rescue_case_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rescue_requests.id", ondelete="SET NULL"), nullable=True
    )
    adoption_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("adoption_applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
