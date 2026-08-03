"""ORM model for stored files with S3 integration."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class FileFolder(StrEnum):
    DOGS = "dogs"
    MEDICAL = "medical"
    SHELTERS = "shelters"
    PROFILES = "profiles"
    DOCUMENTS = "documents"
    CERTIFICATES = "certificates"


class StoredFile(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "stored_files"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    object_key: Mapped[str] = mapped_column(
        String(1024), unique=True, nullable=False, index=True
    )
    thumbnail_object_key: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    folder: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_uploaded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )

    __table_args__ = (
        Index("ix_stored_files_entity", "entity_type", "entity_id"),
        Index("ix_stored_files_folder_uploaded", "folder", "uploaded_at"),
    )
