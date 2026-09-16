"""Unit tests for FleetBreakdownReport (ITEM 9e).

Covers:
1. Create breakdown report for existing vehicle.
2. Create breakdown report fails for non-existent vehicle.
3. Get breakdown report by ID.
4. Update breakdown report status, notes, resolution.
5. List / paginate breakdown reports with filters.
6. Router endpoint CRUD execution.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from pawguard.core.exceptions import NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams
from pawguard.modules.auth.dependencies import CurrentUser
from pawguard.modules.auth.models import User
from pawguard.modules.fleet.models import (
    BreakdownSeverity,
    BreakdownStatus,
    FleetBreakdownReport,
    Vehicle,
    VehicleStatus,
    VehicleType,
)
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.router import (
    get_breakdown_report,
    list_breakdown_reports,
    report_breakdown,
    update_breakdown_report,
)
from pawguard.modules.fleet.schemas import (
    BreakdownReportCreate,
    BreakdownReportUpdate,
)
from pawguard.modules.fleet.service import FleetService


@pytest.fixture
def mock_user() -> CurrentUser:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.full_name = "Fleet Manager"
    user.system_role = "admin"
    claims = MagicMock()
    claims.role = "admin"
    claims.user_id = user.id
    return CurrentUser(user=user, claims=claims, db=AsyncMock(), redis=AsyncMock())


@pytest.fixture
def mock_request() -> Request:
    req = MagicMock(spec=Request)
    req.client.host = "127.0.0.1"
    return req


@pytest.mark.asyncio
async def test_create_breakdown_report_service_success() -> None:
    repo = MagicMock(spec=FleetRepository)
    vehicle_id = uuid.uuid4()
    vehicle = Vehicle(
        id=vehicle_id,
        make_model="Ford Transit",
        license_plate="RESCUE-01",
        vehicle_type=VehicleType.RESCUE_VAN,
        status=VehicleStatus.ACTIVE,
        mileage=15000,
    )
    repo.get_vehicle = AsyncMock(return_value=vehicle)
    repo.user_exists = AsyncMock(return_value=True)

    created_reports = []

    async def mock_create(report: FleetBreakdownReport) -> FleetBreakdownReport:
        report.id = uuid.uuid4()
        report.created_at = datetime.now(UTC)
        report.updated_at = datetime.now(UTC)
        created_reports.append(report)
        return report

    repo.create_breakdown_report = AsyncMock(side_effect=mock_create)

    service = FleetService(repository=repo)
    payload = BreakdownReportCreate(
        vehicle_id=vehicle_id,
        breakdown_type="flat_tire",
        severity=BreakdownSeverity.MINOR,
        description="Front left tire punctured on highway route.",
        location="Highway 101, Mile 42",
        notes="Spare tire applied, replacement needed.",
    )

    result = await service.create_breakdown_report(payload, actor_id=uuid.uuid4())
    assert result.vehicle_id == vehicle_id
    assert result.breakdown_type == "flat_tire"
    assert result.severity == BreakdownSeverity.MINOR
    assert result.status == BreakdownStatus.REPORTED
    assert len(created_reports) == 1


@pytest.mark.asyncio
async def test_create_breakdown_report_vehicle_not_found() -> None:
    repo = MagicMock(spec=FleetRepository)
    repo.get_vehicle = AsyncMock(return_value=None)
    service = FleetService(repository=repo)

    payload = BreakdownReportCreate(
        vehicle_id=uuid.uuid4(),
        breakdown_type="engine_failure",
        severity=BreakdownSeverity.CRITICAL,
        description="Engine smoke.",
    )

    with pytest.raises(NotFoundError, match="Vehicle not found"):
        await service.create_breakdown_report(payload)


@pytest.mark.asyncio
async def test_get_and_update_breakdown_report_service() -> None:
    repo = MagicMock(spec=FleetRepository)
    report_id = uuid.uuid4()
    report = FleetBreakdownReport(
        id=report_id,
        vehicle_id=uuid.uuid4(),
        breakdown_type="radiator_leak",
        severity=BreakdownSeverity.MODERATE,
        description="Coolant leak detected.",
        reported_at=datetime.now(UTC),
        status=BreakdownStatus.REPORTED,
    )
    repo.get_breakdown_report = AsyncMock(return_value=report)
    service = FleetService(repository=repo)

    fetched = await service.get_breakdown_report(report_id)
    assert fetched.id == report_id

    update_payload = BreakdownReportUpdate(
        status="resolved",
        notes="Radiator hose replaced and tested.",
    )
    updated = await service.update_breakdown_report(report_id, update_payload)
    assert updated.status == "resolved"
    assert updated.resolved_at is not None
    assert updated.notes == "Radiator hose replaced and tested."


@pytest.mark.asyncio
async def test_router_breakdown_crud(mock_user: CurrentUser, mock_request: Request) -> None:
    repo = MagicMock(spec=FleetRepository)
    vehicle_id = uuid.uuid4()
    vehicle = Vehicle(
        id=vehicle_id,
        make_model="Ford Transit",
        license_plate="RESCUE-01",
        vehicle_type=VehicleType.RESCUE_VAN,
        status=VehicleStatus.ACTIVE,
        mileage=15000,
    )
    repo.get_vehicle = AsyncMock(return_value=vehicle)
    repo.user_exists = AsyncMock(return_value=True)

    report_id = uuid.uuid4()
    saved_report = FleetBreakdownReport(
        id=report_id,
        vehicle_id=vehicle_id,
        driver_id=mock_user.id,
        breakdown_type="brake_failure",
        severity=BreakdownSeverity.CRITICAL,
        description="Brake pads severely worn.",
        location="Sector 7 Depot",
        reported_at=datetime.now(UTC),
        status=BreakdownStatus.REPORTED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.create_breakdown_report = AsyncMock(return_value=saved_report)
    repo.get_breakdown_report = AsyncMock(return_value=saved_report)
    repo.paginate_breakdown_reports = AsyncMock(return_value=([saved_report], 1))

    service = FleetService(repository=repo)

    # POST /fleet/breakdowns
    create_payload = BreakdownReportCreate(
        vehicle_id=vehicle_id,
        breakdown_type="brake_failure",
        severity=BreakdownSeverity.CRITICAL,
        description="Brake pads severely worn.",
        location="Sector 7 Depot",
    )
    post_res = await report_breakdown(
        payload=create_payload,
        request=mock_request,
        current_user=mock_user,
        service=service,
    )
    assert post_res.data.breakdown_type == "brake_failure"
    assert post_res.data.id == report_id

    # GET /fleet/breakdowns/{report_id}
    get_res = await get_breakdown_report(report_id=report_id, service=service)
    assert get_res.data.id == report_id
    assert get_res.data.severity == BreakdownSeverity.CRITICAL

    # GET /fleet/breakdowns
    list_res = await list_breakdown_reports(
        page=PageParams(page=1, page_size=10),
        sort=SortParams(),
        vehicle_id=vehicle_id,
        status=None,
        search=None,
        service=service,
    )
    assert len(list_res.data) == 1
    assert list_res.meta.total == 1

    # PATCH /fleet/breakdowns/{report_id}
    patch_res = await update_breakdown_report(
        report_id=report_id,
        payload=BreakdownReportUpdate(status="resolved"),
        request=mock_request,
        current_user=mock_user,
        service=service,
    )
    assert patch_res.data.status == "resolved"
