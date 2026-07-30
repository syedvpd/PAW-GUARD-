"""Unit tests for FleetService with mocked repository."""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.fleet.models import FleetMaintenance, Vehicle, VehicleStatus
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.schemas import MaintenanceCreate, VehicleCreate, VehicleUpdate
from pawguard.modules.fleet.service import FleetService
from pawguard.services.audit_service import AuditService


def _make_vehicle(**kw):
    now = datetime.now(UTC)
    vals = dict(
        make_model="", license_plate="", status=VehicleStatus.ACTIVE,
        mileage=0, created_at=now, updated_at=now,
    )
    vals.update(kw)
    return Vehicle(**vals)

def _make_maint(**kw):
    now = datetime.now(UTC)
    vals = dict(
        vehicle_id=uuid.uuid4(), service_date=date.today(),
        description="", cost=0.0, created_at=now,
    )
    vals.update(kw)
    return FleetMaintenance(**vals)


class TestFleetService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=FleetRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return FleetService(mock_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_create_vehicle(self, service, mock_repo):
        mock_repo.get_vehicle_by_plate.return_value = None
        vehicle_id = uuid.uuid4()
        mock_repo.create_vehicle.return_value = Vehicle(
            id=vehicle_id, make_model="Toyota Hilux", license_plate="ABC-123",
            status=VehicleStatus.ACTIVE, mileage=0,
        )
        payload = VehicleCreate(make_model="Toyota Hilux", license_plate="ABC-123")
        result = await service.create_vehicle(payload, actor_id=uuid.uuid4())
        assert result.license_plate == "ABC-123"

    @pytest.mark.asyncio
    async def test_create_vehicle_duplicate_plate(self, service, mock_repo):
        mock_repo.get_vehicle_by_plate.return_value = Vehicle(
            id=uuid.uuid4(), make_model="Existing", license_plate="ABC-123",
            status=VehicleStatus.ACTIVE, mileage=0,
        )
        payload = VehicleCreate(make_model="Toyota", license_plate="ABC-123")
        with pytest.raises(ConflictError, match="already exists"):
            await service.create_vehicle(payload)

    @pytest.mark.asyncio
    async def test_update_vehicle(self, service, mock_repo):
        vehicle_id = uuid.uuid4()
        vehicle = Vehicle(
            id=vehicle_id, make_model="Old Model", license_plate="OLD-001",
            status=VehicleStatus.ACTIVE, mileage=1000,
        )
        mock_repo.get_vehicle.return_value = vehicle
        payload = VehicleUpdate(make_model="New Model", mileage=2000)
        result = await service.update_vehicle(vehicle_id, payload, actor_id=uuid.uuid4())
        assert result.make_model == "New Model"

    @pytest.mark.asyncio
    async def test_update_vehicle_not_found(self, service, mock_repo):
        mock_repo.get_vehicle.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_vehicle(uuid.uuid4(), VehicleUpdate())

    @pytest.mark.asyncio
    async def test_update_vehicle_plate_conflict(self, service, mock_repo):
        vehicle_id = uuid.uuid4()
        vehicle = Vehicle(
            id=vehicle_id, make_model="V", license_plate="OLD-001",
            status=VehicleStatus.ACTIVE, mileage=0,
        )
        mock_repo.get_vehicle.return_value = vehicle
        mock_repo.get_vehicle_by_plate.return_value = Vehicle(
            id=uuid.uuid4(), make_model="Other", license_plate="NEW-001",
            status=VehicleStatus.ACTIVE, mileage=0,
        )
        payload = VehicleUpdate(license_plate="NEW-001")
        with pytest.raises(ConflictError, match="already exists"):
            await service.update_vehicle(vehicle_id, payload)

    @pytest.mark.asyncio
    async def test_get_vehicle_found(self, service, mock_repo):
        vehicle_id = uuid.uuid4()
        mock_repo.get_vehicle.return_value = Vehicle(
            id=vehicle_id, make_model="Toyota", license_plate="ABC-123",
            status=VehicleStatus.ACTIVE, mileage=0,
        )
        result = await service.get_vehicle(vehicle_id)
        assert result.id == vehicle_id

    @pytest.mark.asyncio
    async def test_get_vehicle_not_found(self, service, mock_repo):
        mock_repo.get_vehicle.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_vehicle(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_vehicles_paginated(self, service, mock_repo):
        vehicle = _make_vehicle(
            id=uuid.uuid4(), make_model="Toyota", license_plate="ABC-123",
        )
        mock_repo.paginate_vehicles.return_value = ([vehicle], 1)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_vehicles_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_log_maintenance(self, service, mock_repo):
        vehicle_id = uuid.uuid4()
        mock_repo.get_vehicle.return_value = Vehicle(
            id=vehicle_id, make_model="Toyota", license_plate="ABC-123",
            status=VehicleStatus.ACTIVE, mileage=0,
        )
        maint_id = uuid.uuid4()
        mock_repo.create_maintenance.return_value = FleetMaintenance(
            id=maint_id, vehicle_id=vehicle_id, service_date=date.today(),
            description="Oil change", cost=150.0,
        )
        payload = MaintenanceCreate(
            vehicle_id=vehicle_id, service_date=date.today(), description="Oil change", cost=150.0,
        )
        result = await service.log_maintenance(payload, actor_id=uuid.uuid4())
        assert result.description == "Oil change"

    @pytest.mark.asyncio
    async def test_log_maintenance_vehicle_not_found(self, service, mock_repo):
        mock_repo.get_vehicle.return_value = None
        payload = MaintenanceCreate(
            vehicle_id=uuid.uuid4(), service_date=date.today(), description="Oil change",
        )
        with pytest.raises(NotFoundError):
            await service.log_maintenance(payload)

    @pytest.mark.asyncio
    async def test_list_maintenance_paginated(self, service, mock_repo):
        maint = _make_maint(
            id=uuid.uuid4(), vehicle_id=uuid.uuid4(), description="Repair", cost=500.0,
        )
        mock_repo.paginate_maintenance.return_value = ([maint], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_maintenance_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_update_vehicle_status(self, service, mock_repo):
        vehicle_id = uuid.uuid4()
        mock_repo.get_vehicle.return_value = Vehicle(
            id=vehicle_id, make_model="V", license_plate="P-001",
            status=VehicleStatus.ACTIVE, mileage=0,
        )
        mock_repo.update_vehicle_status.return_value = Vehicle(
            id=vehicle_id, make_model="V", license_plate="P-001",
            status=VehicleStatus.IN_MAINTENANCE, mileage=0,
        )
        result = await service.update_vehicle_status(vehicle_id, VehicleStatus.IN_MAINTENANCE, actor_id=uuid.uuid4())
        assert result.status == VehicleStatus.IN_MAINTENANCE

    @pytest.mark.asyncio
    async def test_soft_delete_vehicle(self, service, mock_repo):
        vehicle_id = uuid.uuid4()
        mock_repo.get_vehicle.return_value = Vehicle(
            id=vehicle_id, make_model="V", license_plate="P-001",
            status=VehicleStatus.ACTIVE, mileage=0,
        )
        mock_repo.soft_delete_vehicle.return_value = None
        await service.soft_delete_vehicle(vehicle_id, actor_id=uuid.uuid4())
        mock_repo.soft_delete_vehicle.assert_called_once_with(vehicle_id)

    @pytest.mark.asyncio
    async def test_soft_delete_vehicle_not_found(self, service, mock_repo):
        mock_repo.get_vehicle.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_vehicle(uuid.uuid4())
