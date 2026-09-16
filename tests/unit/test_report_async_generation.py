"""Unit tests for asynchronous report generation and status polling (ITEM 5).

Covers:
1. POST /reports/jobs returns PENDING immediately with a unique job_id and registers background task / ARQ dispatch.
2. Background task execution transitions job from PENDING -> RUNNING -> DONE.
3. Failed job execution transitions job from PENDING -> RUNNING -> FAILED with persisted error state.
4. ARQ worker scheduled job generate_report_job executes execute_report_job.
5. GET /reports/jobs/{job_id} returns the current state of the job and download_url when DONE.
6. Attempting to download incomplete/failed job raises ValidationFailedError.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from pawguard.core.exceptions import ValidationFailedError
from pawguard.modules.auth.dependencies import CurrentUser
from pawguard.modules.auth.models import User
from pawguard.modules.reports.models import JobStatus, ReportJob
from pawguard.modules.reports.router import (
    create_report_job,
    download_report_job,
    execute_report_job,
    get_report_job_status,
)
from pawguard.modules.reports.schemas import ReportFormat, ReportRequest, ReportType
from pawguard.workers.jobs.scheduled_jobs import generate_report_job


@pytest.fixture
def mock_user() -> CurrentUser:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.full_name = "Admin Tester"
    user.system_role = "admin"
    claims = MagicMock()
    claims.role = "admin"
    claims.user_id = user.id
    return CurrentUser(user=user, claims=claims, db=AsyncMock(), redis=AsyncMock())


@pytest.fixture
def mock_request() -> Request:
    req = MagicMock(spec=Request)
    req.client.host = "127.0.0.1"
    req.headers = {"user-agent": "test-agent"}
    return req


@pytest.mark.asyncio
async def test_create_report_job_returns_pending_immediately(mock_user: CurrentUser) -> None:
    """POST /reports/jobs creates a ReportJob row, dispatches background tasks, and returns PENDING."""
    mock_db = AsyncMock()
    added_objects = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
    background_tasks = BackgroundTasks()
    mock_arq = AsyncMock()

    payload = ReportRequest(
        report_type=ReportType.ADOPTION,
        format=ReportFormat.PDF,
        filters={"status": "completed"},
    )

    response = await create_report_job(
        payload=payload,
        background_tasks=background_tasks,
        current_user=mock_user,
        db=mock_db,
        arq_pool=mock_arq,
    )

    assert response.success is True
    assert response.data is not None
    assert response.data.status == JobStatus.PENDING.value
    assert response.data.report_type == "adoption"
    assert response.data.format == "pdf"
    assert response.data.job_id is not None

    # Verify ReportJob was added to database session
    jobs = [o for o in added_objects if isinstance(o, ReportJob)]
    assert len(jobs) == 1
    assert jobs[0].id == response.data.job_id
    assert jobs[0].status == JobStatus.PENDING.value

    # Verify ARQ queue dispatch was initiated exclusively (single queue architecture)
    mock_arq.enqueue_job.assert_awaited_once_with("generate_report_job", str(response.data.job_id))
    assert len(background_tasks.tasks) == 0


@pytest.mark.asyncio
async def test_background_tasks_execution_transitions_job_pending_to_running_to_done(
    mock_user: CurrentUser,
) -> None:
    """Proves executing the BackgroundTasks fallback path when ARQ is unconfigured runs the worker and transitions job to DONE."""
    job_id = uuid.uuid4()
    job_row = ReportJob(
        id=job_id,
        report_type=ReportType.ADOPTION.value,
        format=ReportFormat.PDF.value,
        status=JobStatus.PENDING.value,
        requester_id=mock_user.id,
        filters={"status": "completed"},
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    background_tasks = BackgroundTasks()

    payload = ReportRequest(
        report_type=ReportType.ADOPTION,
        format=ReportFormat.PDF,
        filters={"status": "completed"},
    )

    with patch("pawguard.modules.reports.router.uuid.uuid4", return_value=job_id):
        await create_report_job(
            payload=payload,
            background_tasks=background_tasks,
            current_user=mock_user,
            db=mock_db,
            arq_pool=None,  # Tests the BackgroundTasks fallback path
        )

    # Now execute the registered background task
    assert len(background_tasks.tasks) == 1
    bg_task = background_tasks.tasks[0]

    mock_session = AsyncMock()
    mock_session.in_transaction = MagicMock(return_value=False)
    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.return_value = job_row
    mock_session.execute.return_value = mock_exec_res

    mock_maker = MagicMock()
    mock_maker.return_value.__aenter__.return_value = mock_session
    mock_maker.return_value.__aexit__.return_value = None

    with (
        patch("pawguard.modules.reports.router.AsyncSessionLocal", mock_maker),
        patch("pawguard.modules.reports.router.ReportService") as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.generate_report.return_value = {"download_url": f"reports/adoption_{job_id}.pdf"}
        mock_svc_cls.return_value = mock_svc

        # Execute the background task
        await bg_task()

        assert job_row.status == JobStatus.DONE.value
        assert job_row.result_object_key == f"reports/adoption_{job_id}.pdf"
        assert job_row.completed_at is not None


@pytest.mark.asyncio
async def test_atomic_claim_prevents_duplicate_execution() -> None:
    """Proves atomic claim prevents duplicate execution when job is already claimed by another worker."""
    job_id = uuid.uuid4()
    running_job = ReportJob(
        id=job_id,
        report_type=ReportType.ADOPTION.value,
        format=ReportFormat.PDF.value,
        status=JobStatus.RUNNING.value,
        requester_id=uuid.uuid4(),
        created_at=datetime.now(UTC),
    )

    mock_session = AsyncMock()
    # First query (claim update) returns None because status is already RUNNING, not PENDING
    mock_claim_res = MagicMock()
    mock_claim_res.scalar_one_or_none.return_value = None

    # Second query (fetch existing) returns the already running job
    mock_existing_res = MagicMock()
    mock_existing_res.scalar_one_or_none.return_value = running_job

    mock_session.execute.side_effect = [mock_claim_res, mock_existing_res]

    with patch("pawguard.modules.reports.router.ReportService") as mock_svc_cls:
        res = await execute_report_job(job_id=job_id, db=mock_session)

        # Service was NOT called to generate the report twice
        mock_svc_cls.assert_not_called()
        assert res.id == job_id
        assert res.status == JobStatus.RUNNING.value


@pytest.mark.asyncio
async def test_background_tasks_execution_failure_transitions_to_failed() -> None:
    """Proves when report generation fails, the job transitions from PENDING -> RUNNING -> FAILED with error context."""
    job_id = uuid.uuid4()
    job_row = ReportJob(
        id=job_id,
        report_type=ReportType.MEDICAL.value,
        format=ReportFormat.CSV.value,
        status=JobStatus.PENDING.value,
        requester_id=uuid.uuid4(),
        created_at=datetime.now(UTC),
    )

    mock_session = AsyncMock()
    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.return_value = job_row
    mock_session.execute.return_value = mock_exec_res

    with patch("pawguard.modules.reports.router.ReportService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.generate_report.side_effect = RuntimeError("Storage connection timed out")
        mock_svc_cls.return_value = mock_svc

        res = await execute_report_job(job_id=job_id, db=mock_session)

        assert res.status == JobStatus.FAILED.value
        assert job_row.status == JobStatus.FAILED.value
        assert job_row.completed_at is not None
        assert "Storage connection timed out" in str(job_row.error_message)


@pytest.mark.asyncio
async def test_arq_scheduled_job_generate_report_job_executes_worker() -> None:
    """Proves the ARQ worker job function generate_report_job invokes execute_report_job correctly."""
    job_id = uuid.uuid4()
    ctx = {"redis": AsyncMock()}

    mock_session = AsyncMock()
    mock_session.in_transaction = MagicMock(return_value=False)
    mock_maker = MagicMock()
    mock_maker.return_value.__aenter__.return_value = mock_session
    mock_maker.return_value.__aexit__.return_value = None

    with (
        patch("pawguard.workers.jobs.scheduled_jobs.AsyncSessionLocal", mock_maker),
        patch(
            "pawguard.modules.reports.router.execute_report_job", new_callable=AsyncMock
        ) as mock_exec,
    ):
        mock_exec.return_value = MagicMock(id=job_id, status=JobStatus.DONE.value)

        await generate_report_job(ctx, str(job_id))
        mock_exec.assert_awaited_once_with(job_id, mock_session)


@pytest.mark.asyncio
async def test_execute_report_job_transitions_to_done() -> None:
    """Simulated job execution transitions status from PENDING to DONE with artifact path."""
    job_id = uuid.uuid4()
    mock_job = ReportJob(
        id=job_id,
        report_type=ReportType.INVENTORY.value,
        format=ReportFormat.CSV.value,
        status=JobStatus.PENDING.value,
        requester_id=uuid.uuid4(),
        filters=None,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = mock_job
    mock_db.execute.return_value = mock_exec_result

    with patch("pawguard.modules.reports.router.ReportService") as mock_service_cls:
        mock_svc = AsyncMock()
        mock_svc.generate_report.return_value = {"download_url": f"reports/inventory_{job_id}.csv"}
        mock_service_cls.return_value = mock_svc

        updated_job = await execute_report_job(job_id=job_id, db=mock_db)

        assert updated_job.status == JobStatus.DONE.value
        assert updated_job.result_object_key == f"reports/inventory_{job_id}.csv"
        assert updated_job.completed_at is not None


@pytest.mark.asyncio
async def test_get_report_job_status_done_has_download_url(mock_user: CurrentUser) -> None:
    """GET /reports/jobs/{job_id} includes download_url when status is DONE."""
    job_id = uuid.uuid4()
    mock_job = ReportJob(
        id=job_id,
        report_type=ReportType.MEDICAL.value,
        format=ReportFormat.PDF.value,
        status=JobStatus.DONE.value,
        requester_id=mock_user.id,
        result_object_key=f"reports/medical_{job_id}.pdf",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = mock_job
    mock_db.execute.return_value = mock_exec_result

    response = await get_report_job_status(job_id=job_id, current_user=mock_user, db=mock_db)

    assert response.success is True
    assert response.data.status == JobStatus.DONE.value
    assert response.data.download_url == f"/api/v1/reports/jobs/{job_id}/download"


@pytest.mark.asyncio
async def test_download_report_job_rejects_pending_job(
    mock_user: CurrentUser, mock_request: Request
) -> None:
    """Attempting to download a job that is still PENDING raises ValidationFailedError."""
    job_id = uuid.uuid4()
    mock_job = ReportJob(
        id=job_id,
        report_type=ReportType.ADOPTION.value,
        format=ReportFormat.PDF.value,
        status=JobStatus.PENDING.value,
        requester_id=mock_user.id,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = mock_job
    mock_db.execute.return_value = mock_exec_result

    with pytest.raises(ValidationFailedError, match="not ready for download"):
        await download_report_job(
            job_id=job_id,
            request=mock_request,
            current_user=mock_user,
            audit=AsyncMock(),
            db=mock_db,
        )
