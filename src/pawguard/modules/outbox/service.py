"""Service logic for coordinating transactional outbox events."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)


class OutboxService:
    """Service to coordinate saving and reliable dispatching of transactional outbox events."""

    @staticmethod
    async def enqueue_job(session: AsyncSession, job_name: str, **payload: Any) -> OutboxEvent:
        """Saves a pending job event to the database outbox table.

        Must be called within an active database transaction session.
        """
        event = OutboxEvent(
            job_name=job_name,
            payload=payload,
            status="pending",
            retry_count=0,
        )
        session.add(event)
        # Flush to generate ID and created_at timestamps inside the transaction
        await session.flush()
        logger.debug(f"Outbox job enqueued in DB transaction: {job_name}")
        return event

    @staticmethod
    async def process_pending_events(
        session: AsyncSession, arq_pool: Any, batch_size: int = 50
    ) -> int:
        """Polls for pending outbox events using a concurrency-safe locking pattern.

        Enqueues each locked event to the target ARQ Redis queue.
        Uses SELECT ... FOR UPDATE SKIP LOCKED to prevent duplicate processing by
        multiple concurrent worker processes.
        """
        # Lock and retrieve pending outbox events
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending")
            .order_by(OutboxEvent.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        result = await session.execute(stmt)
        events = result.scalars().all()

        if not events:
            return 0

        logger.info(f"Outbox processing batch of {len(events)} events.")

        processed_count = 0
        for event in events:
            # Transition state to processing
            event.status = "processing"
            await session.flush()

            try:
                # Dispatch the job to ARQ (Redis)
                if arq_pool:
                    await arq_pool.enqueue_job(event.job_name, **event.payload)
                else:
                    logger.warning(
                        f"No ARQ pool available. Dropping outbox event: {event.job_name}"
                    )

                # Update status on success
                event.status = "completed"
                event.processed_at = datetime.now(UTC)
                processed_count += 1
            except Exception as e:
                # Track failures and schedule retry
                event.retry_count += 1
                event.last_error = str(e)
                # Keep as pending for retry if below threshold, otherwise mark as failed
                if event.retry_count >= 5:
                    event.status = "failed"
                    logger.error(
                        f"Outbox event {event.id} ({event.job_name}) failed permanently: {e}"
                    )
                else:
                    event.status = "pending"
                    logger.warning(
                        f"Outbox event {event.id} ({event.job_name}) failed transiently. Retry count: {event.retry_count}. Error: {e}"
                    )

            await session.flush()

        return processed_count
