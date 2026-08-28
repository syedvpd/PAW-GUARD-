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
    to = payload.get("to") or payload.get("recipient_email") or payload.get("email")
    if not to:
        raise ValueError(f"Missing recipient email address in payload for job '{job_name}'.")

    subject = payload.get("subject")
    if "html_body" in payload and payload["html_body"]:
        subject = subject or "PawGuard Notification"
        await asyncio.to_thread(
            email_svc.send, to=to, subject=subject, html_body=payload["html_body"]
        )
    elif "template_name" in payload and payload["template_name"]:
        template_name = payload["template_name"]
        context = payload.get("context") or payload
        subject = subject or "PawGuard Notification"
        html = email_svc.render(template_name, context)
        await asyncio.to_thread(email_svc.send, to=to, subject=subject, html_body=html)
    elif job_name == "send_password_reset_email_job":
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
    else:
        # Default notification template for all modules across PawGuard
        subject = subject or "PawGuard Notification"
        body = payload.get("body") or payload.get("message") or ""
        html = email_svc.render("notification.html", {"subject": subject, "body": body})
        await asyncio.to_thread(email_svc.send, to=to, subject=subject, html_body=html)


async def _dispatch_job_direct(job_name: str, payload: dict[str, Any]) -> None:
    """Dispatches any ARQ background job name directly in-process as a fallback."""
    is_email_job = (
        "email" in job_name
        or "notification" in job_name
        or job_name.startswith("send_")
    )
    if is_email_job:
        await _dispatch_email_direct(job_name, payload)
        return

    ctx: dict[str, Any] = {}
    if job_name == "broadcast_lost_pet_alert":
        from pawguard.workers.jobs.lost_found_jobs import broadcast_lost_pet_alert
        await broadcast_lost_pet_alert(ctx, **payload)
    elif job_name == "notify_safety_tag_scan":
        from pawguard.workers.jobs.companion_pet_jobs import notify_safety_tag_scan
        await notify_safety_tag_scan(ctx, **payload)
    elif job_name == "send_companion_pet_reminders":
        from pawguard.workers.jobs.companion_pet_jobs import send_companion_pet_reminders
        await send_companion_pet_reminders(ctx, **payload)
    elif job_name == "check_inventory_low_stock":
        from pawguard.workers.jobs.scheduled_jobs import check_inventory_low_stock
        await check_inventory_low_stock(ctx, **payload)
    elif job_name == "check_inventory_expiry":
        from pawguard.workers.jobs.scheduled_jobs import check_inventory_expiry
        await check_inventory_expiry(ctx, **payload)
    elif job_name == "check_vaccination_renewals":
        from pawguard.workers.jobs.scheduled_jobs import check_vaccination_renewals
        await check_vaccination_renewals(ctx, **payload)
    elif job_name == "post_adoption_followups":
        from pawguard.workers.jobs.scheduled_jobs import post_adoption_followups
        await post_adoption_followups(ctx, **payload)
    elif job_name == "process_sponsorship_charges":
        from pawguard.workers.jobs.scheduled_jobs import process_sponsorship_charges
        await process_sponsorship_charges(ctx, **payload)
    elif job_name == "send_volunteer_shift_reminders":
        from pawguard.workers.jobs.scheduled_jobs import send_volunteer_shift_reminders
        await send_volunteer_shift_reminders(ctx, **payload)
    else:
        raise ValueError(f"Unknown in-process job to dispatch directly: {job_name}")


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
                from pawguard.core.config import get_settings
                settings = get_settings()

                is_null_pool = (
                    arq_pool is None
                    or type(arq_pool).__name__ == "_NullArqPool"
                    or getattr(arq_pool, "_inner", None).__class__.__name__ == "_NullArqPool"
                )

                if settings.force_in_process_jobs:
                    logger.info(f"Forcing in-process dispatch for job {event.job_name}")
                    await _dispatch_job_direct(event.job_name, event.payload)
                elif is_null_pool:
                    if settings.environment == "test":
                        logger.info("Test environment: skipping in-process dispatch fallback")
                    else:
                        logger.info(
                            f"Directly dispatching job {event.job_name} in-process (null pool)"
                        )
                        await _dispatch_job_direct(event.job_name, event.payload)
                elif arq_pool:
                    res = await arq_pool.enqueue_job(event.job_name, **event.payload)
                    if res is None:
                        if settings.environment == "test":
                            logger.info("Test environment: skipping arq pool fallback in-process dispatch")
                        else:
                            logger.info(
                                f"ARQ pool fallback: directly dispatching job {event.job_name} in-process"
                            )
                            await _dispatch_job_direct(event.job_name, event.payload)
                else:
                    if settings.environment == "test":
                        logger.info("Test environment: skipping no arq pool fallback in-process dispatch")
                    else:
                        logger.info(
                            f"No ARQ pool: directly dispatching job {event.job_name} in-process"
                        )
                        await _dispatch_job_direct(event.job_name, event.payload)

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
