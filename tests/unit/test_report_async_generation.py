"""Unit tests for asynchronous report generation and status polling (ITEM 5).

Covers:
1. POST /reports/jobs returns PENDING immediately with a unique job_id.
2. GET /reports/jobs/{job_id} returns the current state of the job.
3. Job execution pipeline transitions job to DONE and populates download artifact.
4. Attempting to download incomplete/failed job raises ValidationFailedError.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
    """POST /reports/jobs creates a ReportJob row and returns PENDING immediately."""
    mock_db = AsyncMock()
    added_objects = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    payload = ReportRequest(
        report_type=ReportType.ADOPTION,
        format=ReportFormat.PDF,
        filters={"status": "completed"},
    )

    response = await create_report_job(
        payload=payload,
        current_user=mock_user,
        db=mock_db,
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
async def test_get_report_job_status_done_has_download_url() -> None:
    """GET /reports/jobs/{job_id} includes download_url when status is DONE."""
    job_id = uuid.uuid4()
    mock_job = ReportJob(
        id=job_id,
        report_type=ReportType.MEDICAL.value,
        format=ReportFormat.PDF.value,
        status=JobStatus.DONE.value,
        requester_id=uuid.uuid4(),
        result_object_key=f"reports/medical_{job_id}.pdf",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = mock_job
    mock_db.execute.return_value = mock_exec_result

    response = await get_report_job_status(job_id=job_id, db=mock_db)

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
