"""Unit tests for public rescue tracking and dynamic ETA calculation."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import NotFoundError
from pawguard.modules.rescue.models import RescueRequest, RescueSeverity, RescueStatus
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.service import RescueService


@pytest.fixture
def mock_repo():
    repo = AsyncMock(spec=RescueRepository)
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def rescue_service(mock_repo):
    return RescueService(mock_repo)


@pytest.mark.asyncio
async def test_public_tracking_reported_has_no_eta(rescue_service, mock_repo):
    req_id = uuid.uuid4()
    req = RescueRequest(
        id=req_id,
        ticket_number="RES-20260901-001",
        reporter_name="Jane",
        reporter_phone="+1234567890",
        location_address="123 Maple Street",
        animal_count=1,
        severity=RescueSeverity.HIGH,
        is_urgent=True,
        status=RescueStatus.REPORTED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_repo.get_request_by_ticket.return_value = req

    status = await rescue_service.get_public_status_by_ticket("RES-20260901-001")
    assert status.ticket_number == "RES-20260901-001"
    assert status.status == RescueStatus.REPORTED
    assert status.estimated_arrival_minutes is None
    assert status.eta_display is None


@pytest.mark.asyncio
async def test_public_tracking_dispatched_has_dynamic_eta(rescue_service, mock_repo):
    req_id = uuid.uuid4()
    req = RescueRequest(
        id=req_id,
        ticket_number="RES-20260901-002",
        reporter_name="John",
        reporter_phone="+1234567890",
        location_address="456 Oak Avenue",
        animal_count=2,
        severity=RescueSeverity.CRITICAL,
        is_urgent=True,
        status=RescueStatus.DISPATCHED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_repo.get_request_by_ticket.return_value = req

    status = await rescue_service.get_public_status_by_ticket("RES-20260901-002")
    assert status.ticket_number == "RES-20260901-002"
    assert status.status == RescueStatus.DISPATCHED
    assert status.estimated_arrival_minutes == 15
    assert status.eta_display is not None


@pytest.mark.asyncio
async def test_public_tracking_invalid_ticket_raises_not_found(rescue_service, mock_repo):
    mock_repo.get_request_by_ticket.return_value = None
    mock_repo.get_request_by_id.return_value = None

    with pytest.raises(NotFoundError, match="Rescue report 'NONEXISTENT' not found"):
        await rescue_service.get_public_status_by_ticket("NONEXISTENT")
