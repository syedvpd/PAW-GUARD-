"""Unit tests for the Transactional Outbox Pattern."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.outbox.models import OutboxEvent
from pawguard.modules.outbox.service import OutboxService


class MockArqPool:
    def __init__(self, should_fail=False):
        self.enqueued_jobs = []
        self.should_fail = should_fail

    async def enqueue_job(self, job_name, **payload):
        if self.should_fail:
            raise RuntimeError("Redis connection failure")
        self.enqueued_jobs.append((job_name, payload))


@pytest.mark.asyncio
async def test_outbox_enqueue_job(db_session: AsyncSession):
    """OutboxService.enqueue_job must insert a pending record inside the database transaction."""
    job_name = "test_email_verification"
    payload = {"to": "user@example.com", "url": "http://verify"}

    event = await OutboxService.enqueue_job(db_session, job_name, **payload)
    assert event.id is not None
    assert event.job_name == job_name
    assert event.payload == payload
    assert event.status == "pending"
    assert event.retry_count == 0

    # Retrieve from DB to verify persistence
    stmt = select(OutboxEvent).where(OutboxEvent.id == event.id)
    db_event = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_event is not None
    assert db_event.status == "pending"


@pytest.mark.asyncio
async def test_outbox_process_pending_events_success(db_session: AsyncSession):
    """Pending events must be enqueued to ARQ Redis and marked completed with a processed timestamp."""
    job_name = "test_verification"
    payload = {"to": "user@example.com"}

    # 1. Enqueue job
    await OutboxService.enqueue_job(db_session, job_name, **payload)
    await db_session.commit()

    # 2. Process pending events
    arq_pool = MockArqPool()
    processed_count = await OutboxService.process_pending_events(db_session, arq_pool)
    assert processed_count == 1
    assert len(arq_pool.enqueued_jobs) == 1
    assert arq_pool.enqueued_jobs[0] == (job_name, payload)

    # 3. Verify event updated to completed in DB
    stmt = select(OutboxEvent).where(OutboxEvent.job_name == job_name, OutboxEvent.status == "completed")
    db_event = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_event is not None
    assert db_event.processed_at is not None


@pytest.mark.asyncio
async def test_outbox_process_pending_events_transient_failure(db_session: AsyncSession):
    """If ARQ enqueue fails, the event retry_count must increment, logging the error, and stay in pending state."""
    job_name = "test_transient"
    payload = {"to": "retry@example.com"}

    await OutboxService.enqueue_job(db_session, job_name, **payload)
    await db_session.commit()

    # Process with a failing ARQ pool
    failing_arq = MockArqPool(should_fail=True)
    processed_count = await OutboxService.process_pending_events(db_session, failing_arq)
    assert processed_count == 0

    # Verify event remains pending but retry count incremented
    stmt = select(OutboxEvent).where(OutboxEvent.job_name == job_name)
    db_event = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_event is not None
    assert db_event.status == "pending"
    assert db_event.retry_count == 1
    assert "Redis connection failure" in db_event.last_error


@pytest.mark.asyncio
async def test_outbox_process_pending_events_permanent_failure(db_session: AsyncSession):
    """If retry limit (5) is reached, the outbox event status must transition to 'failed' permanently."""
    job_name = "test_permanent"
    payload = {"to": "fail@example.com"}

    event = await OutboxService.enqueue_job(db_session, job_name, **payload)
    event.retry_count = 4  # Simulate 4 previous failures
    await db_session.commit()

    # Process 5th attempt with failing ARQ pool
    failing_arq = MockArqPool(should_fail=True)
    processed_count = await OutboxService.process_pending_events(db_session, failing_arq)
    assert processed_count == 0

    # Verify status changed to failed
    stmt = select(OutboxEvent).where(OutboxEvent.job_name == job_name)
    db_event = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_event is not None
    assert db_event.status == "failed"
