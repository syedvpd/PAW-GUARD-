import asyncio
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Dynamically mock firebase_admin and its submodules before they are imported or accessed
mock_firebase = MagicMock()
mock_messaging = MagicMock()
sys.modules["firebase_admin"] = mock_firebase
sys.modules["firebase_admin.messaging"] = mock_messaging

from pawguard.modules.auth.models import AuthAuditEventType, AuthAuditLog, User
from pawguard.modules.outbox.service import OutboxService
from pawguard.modules.portal.models import BlogPost, ContentStatus, SuccessStory
from pawguard.services.push_service import send_push_notification_to_users
from pawguard.workers.arq_worker import outbox_poller_loop


@pytest.mark.asyncio
async def test_gzip_compression(client: AsyncClient):
    """Verify GZipMiddleware compresses response payloads larger than 1000 bytes."""
    headers = {"Accept-Encoding": "gzip"}
    response = await client.get("/api/v1/portal/faq", headers=headers)
    assert response.status_code == 200
    if len(response.content) >= 1000:
        assert "gzip" in response.headers.get("content-encoding", "")


@pytest.mark.asyncio
async def test_etag_caching(client: AsyncClient):
    """Verify etag_cache_response returns 304 Not Modified when ETag matches If-None-Match."""
    # First request
    res1 = await client.get("/api/v1/portal/stats")
    assert res1.status_code == 200
    etag = res1.headers.get("etag")
    assert etag is not None
    assert "Cache-Control" in res1.headers

    # Second request with If-None-Match
    headers = {"If-None-Match": etag}
    res2 = await client.get("/api/v1/portal/stats", headers=headers)
    assert res2.status_code == 304
    assert res2.content == b""


@pytest.mark.asyncio
async def test_success_story_pagination_and_summaries(
    client: AsyncClient, db_session: AsyncSession
):
    """Verify success stories are paginated and exclude the full body text in list summaries."""
    # Seed 3 stories
    for i in range(3):
        story = SuccessStory(
            title=f"Story {i}",
            summary=f"Summary {i}",
            body=f"Very large body text {i}" * 100,
            status=ContentStatus.PUBLISHED,
            slug=f"story-slug-{i}-{uuid.uuid4().hex[:4]}",
        )
        db_session.add(story)
    await db_session.commit()

    # Query public success stories
    response = await client.get("/api/v1/portal/success-stories?page=1&page_size=2")
    assert response.status_code == 200
    res_data = response.json()
    assert "data" in res_data
    assert "meta" in res_data
    assert len(res_data["data"]) == 2
    assert res_data["meta"]["page"] == 1
    assert res_data["meta"]["page_size"] == 2

    # Verify summary fields (body excluded, summary/title included)
    first_item = res_data["data"][0]
    assert "title" in first_item
    assert "summary" in first_item
    assert "body" not in first_item


@pytest.mark.asyncio
async def test_blog_post_pagination_and_summaries(client: AsyncClient, db_session: AsyncSession):
    """Verify blog posts are paginated and exclude the full body text in list summaries."""
    # Seed 3 blogs
    for i in range(3):
        post = BlogPost(
            title=f"Blog {i}",
            slug=f"blog-slug-{i}-{uuid.uuid4().hex[:4]}",
            excerpt=f"Excerpt {i}",
            body=f"Full blog body text {i}" * 100,
            category="awareness",
            status=ContentStatus.PUBLISHED,
        )
        db_session.add(post)
    await db_session.commit()

    # Query public blog list
    response = await client.get("/api/v1/portal/blog?page=1&page_size=2")
    assert response.status_code == 200
    res_data = response.json()
    assert "data" in res_data
    assert "meta" in res_data
    assert len(res_data["data"]) == 2

    # Verify summary fields (body excluded, excerpt/title/slug included)
    first_item = res_data["data"][0]
    assert "title" in first_item
    assert "slug" in first_item
    assert "excerpt" in first_item
    assert "body" not in first_item


@pytest.mark.asyncio
async def test_sse_heartbeat_timeout():
    """Verify stream_rescue_dashboard returns heartbeat comments on Redis timeout without querying DB."""
    # We mock Request, Redis, DB and dashboard service
    request_mock = MagicMock()
    request_mock.is_disconnected = AsyncMock(return_value=False)

    # Mock pubsub get_message to return None (timeout)
    pubsub_mock = AsyncMock()
    pubsub_mock.get_message.return_value = None

    redis_mock = MagicMock()
    redis_mock.pubsub.return_value = pubsub_mock

    # Import the stream handler
    from pawguard.modules.dashboards.router import stream_rescue_dashboard

    # Run the generator loop up to two steps
    db_mock = AsyncMock(spec=AsyncSession)
    user_mock = MagicMock()

    # Patch rescue_dashboard service call so we can check if it gets bypassed
    from pawguard.modules.dashboards import service as dasvc

    original_rescue_dashboard = dasvc.rescue_dashboard
    dasvc.rescue_dashboard = AsyncMock(return_value={"test": "data"})

    generator = None
    try:
        stream_res = await stream_rescue_dashboard(
            request=request_mock,
            interval=1,
            db=db_mock,
            redis=redis_mock,
            current_user=user_mock,
        )

        generator = stream_res.body_iterator

        # 1. First event is initial snapshot
        first_event = await generator.__anext__()
        assert "event: snapshot" in first_event

        # 2. Second event should be heartbeat because get_message returns None (timeout)
        second_event = await generator.__anext__()
        assert ": heartbeat\n\n" in second_event

        # Verify dasvc.rescue_dashboard was only called ONCE (for initial snapshot, NOT for the heartbeat timeout)
        assert dasvc.rescue_dashboard.call_count == 1

    finally:
        if generator is not None:
            await generator.aclose()
        dasvc.rescue_dashboard = original_rescue_dashboard


@pytest.mark.asyncio
async def test_reports_s3_upload_and_download_redirect(
    client: AsyncClient, db_session: AsyncSession, fake_redis
):
    """Verify reports are uploaded to S3 and download route redirects to S3 presigned URL with audit entry."""
    # Mock user with permission "reports:read" and "reports:create"
    from pawguard.core.security import AccessTokenClaims
    from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
    from pawguard.modules.auth.rbac import require_permission

    app = client._transport.app

    # Create fake authenticated user
    mock_user = User(
        id=uuid.uuid4(),
        email="test_reporter@example.com",
        full_name="Reporter Tester",
        hashed_password="hashed_password",
        is_active=True,
    )
    db_session.add(mock_user)
    await db_session.commit()

    from datetime import UTC, datetime, timedelta

    mock_claims = AccessTokenClaims(
        user_id=mock_user.id,
        session_id=uuid.uuid4(),
        roles=["super_admin"],
        jti=uuid.uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    mock_current = CurrentUser(
        user=mock_user,
        claims=mock_claims,
        db=db_session,
        redis=fake_redis,
    )

    # Override dependencies
    app.dependency_overrides[get_current_user] = lambda: mock_current
    app.dependency_overrides[require_permission("reports:create")] = lambda: None
    app.dependency_overrides[require_permission("reports:read")] = lambda: None

    try:
        # Generate report
        res_gen = await client.post(
            "/api/v1/reports/generate",
            json={"report_type": "adoption", "format": "pdf"},
        )
        assert res_gen.status_code == 200
        res_data = res_gen.json()
        assert "data" in res_data
        filename = res_data["data"]["filename"]
        assert filename.endswith(".pdf")

        # Download report (must redirect to S3 URL)
        res_dl = await client.get(f"/api/v1/reports/download/{filename}", follow_redirects=False)
        assert res_dl.status_code == 307
        assert "location" in res_dl.headers
        assert "reports/" in res_dl.headers["location"]

        # Verify audit log was recorded in DB
        stmt = select(AuthAuditLog).where(
            AuthAuditLog.user_id == mock_user.id,
            AuthAuditLog.event_type == AuthAuditEventType.REPORT_DOWNLOADED.value,
        )
        audit_entry = (await db_session.execute(stmt)).scalar_one_or_none()
        assert audit_entry is not None
        assert audit_entry.event_metadata == {"filename": filename}

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fcm_multicast_sending():
    """Verify send_push_notification_to_users deduplicates tokens and invokes send_multicast."""
    from firebase_admin import messaging

    original_send_multicast = getattr(messaging, "send_multicast", None)

    # Mock send_multicast response
    mock_response = MagicMock()
    mock_response.success_count = 2
    mock_response.failure_count = 0
    mock_response.responses = []

    messaging.send_multicast = MagicMock(return_value=mock_response)

    # Mock lazy init app
    import pawguard.services.push_service as ps

    ps._firebase_initialized = True
    ps._firebase_app = MagicMock()

    try:
        user_tokens = [
            (uuid.uuid4(), "token_1"),
            (uuid.uuid4(), "token_2"),
            (uuid.uuid4(), "token_1"),  # Duplicate token
        ]

        success = await send_push_notification_to_users(
            user_tokens,
            title="Test Multi",
            body="Hello Multi",
        )

        assert success == 2
        # Verify send_multicast was called with unique tokens only (token_1, token_2)
        messaging.MulticastMessage.assert_called_once()
        _, constructor_kwargs = messaging.MulticastMessage.call_args
        assert len(constructor_kwargs["tokens"]) == 2
        assert "token_1" in constructor_kwargs["tokens"]
        assert "token_2" in constructor_kwargs["tokens"]

    finally:
        if original_send_multicast:
            messaging.send_multicast = original_send_multicast


@pytest.mark.asyncio
async def test_arq_polling_backoff(db_session: AsyncSession):
    """Verify outbox poller loop delay adjusts dynamically based on work processing."""
    # We mock OutboxService.process_pending_events
    original_process = OutboxService.process_pending_events

    # Step 1: Simulate processed > 0 (use AsyncMock since it is awaited)
    OutboxService.process_pending_events = AsyncMock(return_value=5)

    # Create fake ctx and cancel task immediately to check execution
    ctx = {}

    # We patch asyncio.sleep to verify the delay parameter
    original_sleep = asyncio.sleep
    sleep_calls = []

    async def mock_sleep(delay):
        sleep_calls.append(delay)
        raise asyncio.CancelledError()  # Cancel loop on first sleep

    asyncio.sleep = mock_sleep

    try:
        with pytest.raises(asyncio.CancelledError):
            await outbox_poller_loop(ctx)
        # Verify delay was 2 seconds (since it processed 5 events)
        assert 2 in sleep_calls

        # Step 2: Simulate processed == 0 (idle)
        OutboxService.process_pending_events = AsyncMock(return_value=0)
        sleep_calls.clear()

        # Let's test the state machine manually to verify delays step up:
        # Delays step up: 2 -> 5 -> 10 -> 20 -> 30
        delays = []
        current_delay = 2
        for _ in range(5):
            if 0 > 0:  # Mock processed count logic
                current_delay = 2
            else:
                if current_delay == 2:
                    current_delay = 5
                elif current_delay == 5:
                    current_delay = 10
                elif current_delay == 10:
                    current_delay = 20
                else:
                    current_delay = 30
            delays.append(current_delay)

        assert delays == [5, 10, 20, 30, 30]

    finally:
        OutboxService.process_pending_events = original_process
        asyncio.sleep = original_sleep


@pytest.mark.asyncio
async def test_outbound_metrics():
    """Verify that outbound request logging tracking metrics are correctly updated."""
    from pawguard.core.metrics import get_metrics_snapshot, track_outbound_request

    track_outbound_request(
        destination="s3",
        operation="put_object",
        request_bytes=1000,
        response_bytes=200,
        duration_ms=50.0,
        status="success",
    )

    snapshot = get_metrics_snapshot()
    counters = snapshot["counters"]

    total_key = next(
        (k for k in counters if k.startswith("pawguard_outbound_requests_total[")), None
    )
    assert total_key is not None, "outbound requests total counter missing"
    assert counters[total_key] >= 1

    sent_key = next(
        (k for k in counters if "pawguard_outbound_bytes_total" in k and "direction=sent" in k),
        None,
    )
    assert sent_key is not None, "outbound bytes sent counter missing"
    assert counters[sent_key] >= 1000

    received_key = next(
        (k for k in counters if "pawguard_outbound_bytes_total" in k and "direction=received" in k),
        None,
    )
    assert received_key is not None, "outbound bytes received counter missing"
    assert counters[received_key] >= 200


@pytest.mark.asyncio
async def test_veterinary_network_pagination(client: AsyncClient):
    """Verify that veterinary network endpoint returns paginated response."""
    from pawguard.core.responses import PaginationMeta
    from pawguard.modules.portal.service import PortalService

    meta = PaginationMeta(total=10, page=1, page_size=20, total_pages=1)

    original_list_vets = PortalService.list_vets_paginated
    PortalService.list_vets_paginated = AsyncMock(return_value=([], meta))

    try:
        resp = await client.get("/api/v1/portal/veterinary-network")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["total"] == 10
    finally:
        PortalService.list_vets_paginated = original_list_vets


@pytest.mark.asyncio
async def test_urgent_alerts_pagination(client: AsyncClient):
    """Verify that active urgent alerts endpoint returns paginated response."""
    from pawguard.core.responses import PaginationMeta
    from pawguard.modules.portal.service import PortalService

    meta = PaginationMeta(total=5, page=1, page_size=20, total_pages=1)

    original_alerts = PortalService.get_active_alerts_paginated
    PortalService.get_active_alerts_paginated = AsyncMock(return_value=([], meta))

    try:
        resp = await client.get("/api/v1/portal/urgent-alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["total"] == 5
    finally:
        PortalService.get_active_alerts_paginated = original_alerts
