"""Outbox event model for transactional message guarantee."""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pawguard.db.base import Base
from pawguard.db.mixins import UUIDPkMixin, TimestampMixin


class OutboxEvent(UUIDPkMixin, TimestampMixin, Base):
    """Database record for background tasks enqueued within a transaction.

    This ensures that database operations and background task queueing are atomic.
    """

    __tablename__ = "outbox_events"

    job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)  # pending, processing, completed, failed
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
