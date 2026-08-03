"""Unit tests for FleetService with mocked repository."""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.fleet.models import (
    EquipmentCheckout,
    FleetMaintenance,
    FuelLog,
    Vehicle,
    VehicleStatus,
)
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.schemas import (
    EquipmentCheckoutCreate,
    EquipmentReturnRequest,
    FuelLogCreate,
    MaintenanceCreate,
    VehicleCreate,
    VehicleUpdate,
)
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

    @pytest.mark.asyncio
    async def test_checkout_equipment(self, service, mock_repo):
        checkout_id = uuid.uuid4()
        mock_repo.create_equipment_checkout.return_value = EquipmentCheckout(
            id=checkout_id, equipment_name="Net Gun", checked_out_at=datetime.now(UTC),
        )
        payload = EquipmentCheckoutCreate(equipment_name="Net Gun")
        result = await service.checkout_equipment(payload, actor_id=uuid.uuid4())
        assert result.equipment_name == "Net Gun"
        assert result.returned_at is None

    @pytest.mark.asyncio
    async def test_checkout_equipment_vehicle_not_found(self, service, mock_repo):
        mock_repo.get_vehicle.return_value = None
        payload = EquipmentCheckoutCreate(equipment_name="Net Gun", assigned_to_vehicle_id=uuid.uuid4())
        with pytest.raises(NotFoundError):
            await service.checkout_equipment(payload)

    @pytest.mark.asyncio
    async def test_return_equipment(self, service, mock_repo):
        checkout_id = uuid.uuid4()
        mock_repo.get_equipment_checkout.return_value = EquipmentCheckout(
            id=checkout_id, equipment_name="Net Gun", checked_out_at=datetime.now(UTC),
        )
        result = await service.return_equipment(
            checkout_id, EquipmentReturnRequest(), actor_id=uuid.uuid4()
        )
        assert result.returned_at is not None

    @pytest.mark.asyncio
    async def test_return_equipment_not_found(self, service, mock_repo):
        mock_repo.get_equipment_checkout.return_value = None
        with pytest.raises(NotFoundError):
            await service.return_equipment(uuid.uuid4(), EquipmentReturnRequest())

    @pytest.mark.asyncio
    async def test_return_equipment_already_returned(self, service, mock_repo):
        checkout_id = uuid.uuid4()
        mock_repo.get_equipment_checkout.return_value = EquipmentCheckout(
            id=checkout_id, equipment_name="Net Gun", checked_out_at=datetime.now(UTC),
            returned_at=datetime.now(UTC),
        )
        with pytest.raises(ConflictError, match="already been returned"):
            await service.return_equipment(checkout_id, EquipmentReturnRequest())

    @pytest.mark.asyncio
    async def test_checkout_equipment_for_dispatch(self, service, mock_repo):
        """Dispatch equipment auto-checkout creates rows linked to the dispatch,
        trims names, and leaves them outstanding."""
        dispatch_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        mock_repo.create_equipment_checkout.side_effect = [
            EquipmentCheckout(id=uuid.uuid4(), equipment_name="Net Gun", checked_out_at=datetime.now(UTC)),
            EquipmentCheckout(id=uuid.uuid4(), equipment_name="Crate", checked_out_at=datetime.now(UTC)),
            EquipmentCheckout(id=uuid.uuid4(), equipment_name="Trap", checked_out_at=datetime.now(UTC)),
        ]
        records = await service.checkout_equipment_for_dispatch(
            rescue_dispatch_id=dispatch_id,
            equipment_names=["Net Gun", " Crate ", "Trap"],
            assigned_to_agent_id=agent_id,
            actor_id=uuid.uuid4(),
        )
        assert len(records) == 3
        assert mock_repo.create_equipment_checkout.call_count == 3
        created = mock_repo.create_equipment_checkout.call_args_list[1].args[0]
        assert created.equipment_name == "Crate"
        assert created.rescue_dispatch_id == dispatch_id
        assert created.assigned_to_agent_id == agent_id
        assert created.returned_at is None

    @pytest.mark.asyncio
    async def test_checkout_equipment_for_dispatch_empty_names(self, service, mock_repo):
        """No equipment names means no checkout rows."""
        records = await service.checkout_equipment_for_dispatch(
            rescue_dispatch_id=uuid.uuid4(), equipment_names=[],
        )
        assert records == []
        mock_repo.create_equipment_checkout.assert_not_called()

    @pytest.mark.asyncio
    async def test_checkout_equipment_for_dispatch_vehicle_not_found(self, service, mock_repo):
        """Auto-checkout still validates the target vehicle like manual checkout."""
        mock_repo.get_vehicle.return_value = None
        with pytest.raises(NotFoundError):
            await service.checkout_equipment_for_dispatch(
                rescue_dispatch_id=uuid.uuid4(),
                equipment_names=["Net Gun"],
                assigned_to_vehicle_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_release_equipment_for_dispatch(self, service, mock_repo, mock_audit):
        """Release marks outstanding dispatch equipment returned and audits."""
        dispatch_id = uuid.uuid4()
        mock_repo.release_equipment_for_dispatch.return_value = 3
        count = await service.release_equipment_for_dispatch(
            rescue_dispatch_id=dispatch_id, actor_id=uuid.uuid4(),
        )
        assert count == 3
        assert mock_repo.release_equipment_for_dispatch.call_args[0][0] == dispatch_id
        mock_audit.record.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_release_equipment_for_dispatch_none_outstanding(self, service, mock_repo, mock_audit):
        """No outstanding equipment for the dispatch -> no audit noise."""
        mock_repo.release_equipment_for_dispatch.return_value = 0
        count = await service.release_equipment_for_dispatch(rescue_dispatch_id=uuid.uuid4())
        assert count == 0
        mock_audit.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_equipment_checkouts_paginated(self, service, mock_repo):
        record = EquipmentCheckout(
            id=uuid.uuid4(), equipment_name="Trap", checked_out_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        mock_repo.paginate_equipment_checkouts.return_value = ([record], 1)
        result = await service.list_equipment_checkouts_paginated(PageParams(), SortParams())
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1


class TestFleetFuelLogs:
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
    async def test_log_fuel_success(self, service, mock_repo):
        vehicle_id = uuid.uuid4()
        mock_repo.get_vehicle.return_value = Vehicle(
            id=vehicle_id, make_model="Toyota Hilux", license_plate="ABC-123",
            status=VehicleStatus.ACTIVE, mileage=5000,
        )
        log_id = uuid.uuid4()
        filled_at = datetime.now(UTC)
        mock_repo.create_fuel_log.return_value = FuelLog(
            id=log_id, vehicle_id=vehicle_id, filled_by_id=uuid.uuid4(),
            fuel_type="diesel", volume_litres=50.0, cost=7500.0,
            mileage_at_fill=5100, filled_at=filled_at,
            created_at=filled_at, updated_at=filled_at,
        )
        payload = FuelLogCreate(
            fuel_type="diesel", volume_litres=50.0, cost=7500.0, mileage_at_fill=5100,
        )
        result = await service.log_fuel(vehicle_id, payload, actor_id=uuid.uuid4())
        assert result.fuel_type == "diesel"
        assert result.volume_litres == 50.0

    @pytest.mark.asyncio
    async def test_log_fuel_updates_mileage(self, service, mock_repo):
        vehicle_id = uuid.uuid4()
        vehicle = Vehicle(
            id=vehicle_id, make_model="Toyota Hilux", license_plate="ABC-123",
            status=VehicleStatus.ACTIVE, mileage=5000,
        )
        mock_repo.get_vehicle.return_value = vehicle
        payload = FuelLogCreate(
            fuel_type="petrol", volume_litres=40.0, cost=6000.0, mileage_at_fill=5500,
        )
        mock_repo.create_fuel_log.return_value = FuelLog(
            id=uuid.uuid4(), vehicle_id=vehicle_id, filled_by_id=uuid.uuid4(),
            fuel_type="petrol", volume_litres=40.0, cost=6000.0,
            mileage_at_fill=5500, filled_at=datetime.now(UTC),
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        await service.log_fuel(vehicle_id, payload, actor_id=uuid.uuid4())
        assert vehicle.mileage == 5500

    @pytest.mark.asyncio
    async def test_log_fuel_vehicle_not_found(self, service, mock_repo):
        mock_repo.get_vehicle.return_value = None
        payload = FuelLogCreate(
            fuel_type="diesel", volume_litres=50.0, cost=7500.0, mileage_at_fill=5100,
        )
        with pytest.raises(NotFoundError):
            await service.log_fuel(uuid.uuid4(), payload)
