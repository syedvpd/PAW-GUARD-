"""ORM models for public portal CMS content."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class ContentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class LegalDocumentType(StrEnum):
    TERMS = "terms"
    PRIVACY = "privacy"
    ADOPTION = "adoption"
    FOSTER = "foster"
    VOLUNTEER = "volunteer"
    DONATION = "donation"
    OTHER = "other"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SuccessStory(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "success_stories"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    hero_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dog_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dog_profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ContentStatus] = mapped_column(
        String(32), default=ContentStatus.DRAFT, nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BlogPost(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "blog_posts"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(
        String(128), default="awareness", nullable=False, index=True
    )
    status: Mapped[ContentStatus] = mapped_column(
        String(32), default=ContentStatus.DRAFT, nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VeterinaryPartner(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "veterinary_partners"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    services: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class ContactLocation(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "contact_locations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operating_hours: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_emergency_hotline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class FAQEntry(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "faq_entries"

    question: Mapped[str] = mapped_column(String(512), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(128), default="general", nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class LegalDocument(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Legal framework content: terms of service, privacy policy, adoption
    contracts, etc. Published documents are served publicly (no auth); drafts
    are only visible to admins.
    """

    __tablename__ = "legal_documents"

    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[LegalDocumentType] = mapped_column(
        String(32), default=LegalDocumentType.OTHER, nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0", nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        String(32), default=ContentStatus.DRAFT, nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UrgentAlert(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Urgent alert banner shown on the public site (PRR §6.1). Only alerts
    that are active and inside their scheduled window are served publicly.
    """

    __tablename__ = "urgent_alerts"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        String(16), default=AlertSeverity.INFO, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
