"""Service logic for coordinating transactional outbox events."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.outbox.models import OutboxEvent
from pawguard.services.email_service import EmailService

logger = logging.getLogger(__name__)


async def _dispatch_email_direct(job_name: str, payload: dict[str, Any]) -> None:
    email_svc = EmailService()
    to = payload.get("to")
    if not to:
        raise ValueError("Missing 'to' address in email payload.")

    if job_name == "send_password_reset_email_job":
        reset_url = payload.get("reset_url", "")
        html = email_svc.render("password_reset.html", {"reset_url": reset_url})
        await asyncio.to_thread(
            email_svc.send, to=to, subject="Reset your PawGuard password", html_body=html
        )
    elif job_name == "send_email_verification_email_job":
        verify_url = payload.get("verify_url", "")
        html = email_svc.render("email_verification.html", {"verify_url": verify_url})
        await asyncio.to_thread(
            email_svc.send, to=to, subject="Verify your PawGuard email", html_body=html
        )
    elif job_name == "send_notification_email_job":
        subject = payload.get("subject", "PawGuard Notification")
        body = payload.get("body", "")
        html = email_svc.render("notification.html", {"subject": subject, "body": body})
        await asyncio.to_thread(email_svc.send, to=to, subject=subject, html_body=html)
    else:
        raise ValueError(f"Unknown email job type: {job_name}")


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

        Enqueues each locked event to the target ARQ Redis queue or dispatches
        email jobs directly in-process when ARQ Redis is unreachable.
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
                is_null_pool = (
                    arq_pool is None
                    or type(arq_pool).__name__ == "_NullArqPool"
                    or getattr(arq_pool, "_inner", None).__class__.__name__ == "_NullArqPool"
                )
                is_email_job = event.job_name in (
                    "send_password_reset_email_job",
                    "send_email_verification_email_job",
                    "send_notification_email_job",
                )

                if is_email_job and is_null_pool:
                    logger.info(
                        f"Directly dispatching email job {event.job_name} to {event.payload.get('to')}"
                    )
                    await _dispatch_email_direct(event.job_name, event.payload)
                elif arq_pool and not is_null_pool:
                    res = await arq_pool.enqueue_job(event.job_name, **event.payload)
                    if res is None and is_email_job:
                        logger.info(
                            f"ARQ pool fallback: directly dispatching email job {event.job_name}"
                        )
                        await _dispatch_email_direct(event.job_name, event.payload)
                    elif res is None and not is_email_job:
                        raise RuntimeError(
                            f"ARQ pool unavailable for non-email job {event.job_name}"
                        )
                elif is_email_job:
                    await _dispatch_email_direct(event.job_name, event.payload)
                else:
                    raise RuntimeError(f"No ARQ pool available for job {event.job_name}")

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
