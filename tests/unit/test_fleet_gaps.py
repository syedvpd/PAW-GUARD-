"""Fleet PRR 3.13 gaps: insurance on create, maintenance type, asset register,
breakdown enums and the fleet summary."""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.modules.fleet.models import (
    EquipmentAsset,
    EquipmentCheckout,
    EquipmentCondition,
    FleetMaintenance,
    MaintenanceType,
    Vehicle,
    VehicleStatus,
)
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.schemas import (
    BreakdownReportCreate,
    BreakdownReportUpdate,
    EquipmentCheckoutCreate,
    EquipmentReturnRequest,
    MaintenanceCreate,
    VehicleCreate,
)
from pawguard.modules.fleet.service import FleetService


@pytest.fixture
def repo():
    r = AsyncMock(spec=FleetRepository)
    r._session = AsyncMock()
    return r


@pytest.fixture
def service(repo):
    return FleetService(repo)


def _asset(**kw):
    vals = dict(id=uuid.uuid4(), name="Net Gun #2", condition=EquipmentCondition.GOOD)
    vals.update(kw)
    return EquipmentAsset(**vals)


@pytest.mark.asyncio
async def test_create_vehicle_keeps_insurance_fields(service, repo):
    repo.get_vehicle_by_plate.return_value = None
    repo.create_vehicle.side_effect = lambda v: v
    payload = VehicleCreate(
        make_model="Ford Transit",
        license_plate="AMB-02",
        insurance_provider="SafeGuard",
        insurance_policy_number="POL-1",
        insurance_expiry_date=date(2027, 1, 31),
        insurance_contact_phone="+91-555",
    )
    created = await service.create_vehicle(payload)
    assert created.insurance_provider == "SafeGuard"
    assert created.insurance_policy_number == "POL-1"
    assert created.insurance_expiry_date == date(2027, 1, 31)
    assert created.insurance_contact_phone == "+91-555"


@pytest.mark.asyncio
async def test_maintenance_type_is_persisted(service, repo):
    repo.get_vehicle.return_value = Vehicle(id=uuid.uuid4(), make_model="x", license_plate="y")
    repo.create_maintenance.side_effect = lambda m: m
    record = await service.log_maintenance(
        MaintenanceCreate(
            vehicle_id=uuid.uuid4(),
            service_date=date.today(),
            description="Annual safety inspection",
            maintenance_type="safety_inspection",
        )
    )
    assert isinstance(record, FleetMaintenance)
    assert record.maintenance_type == MaintenanceType.SAFETY_INSPECTION


def test_maintenance_type_defaults_to_service_and_rejects_unknown():
    base = dict(vehicle_id=uuid.uuid4(), service_date=date.today(), description="Oil")
    assert MaintenanceCreate(**base).maintenance_type == MaintenanceType.SERVICE
    with pytest.raises(ValidationError):
        MaintenanceCreate(**base, maintenance_type="car_wash")


def test_breakdown_severity_and_status_are_validated():
    with pytest.raises(ValidationError):
        BreakdownReportCreate(
            vehicle_id=uuid.uuid4(), breakdown_type="Tyre", description="Flat", severity="huge"
        )
    with pytest.raises(ValidationError):
        BreakdownReportUpdate(status="fixed")
    assert BreakdownReportUpdate(status="in_repair").status == "in_repair"


@pytest.mark.asyncio
async def test_checkout_by_asset_uses_asset_name(service, repo):
    asset = _asset()
    repo.get_asset.return_value = asset
    repo.get_outstanding_checkout_for_asset.return_value = None
    repo.create_equipment_checkout.side_effect = lambda c: c
    record = await service.checkout_equipment(EquipmentCheckoutCreate(asset_id=asset.id))
    assert record.asset_id == asset.id
    assert record.equipment_name == "Net Gun #2"


@pytest.mark.asyncio
async def test_checkout_rejects_asset_already_out(service, repo):
    asset = _asset()
    repo.get_asset.return_value = asset
    repo.get_outstanding_checkout_for_asset.return_value = EquipmentCheckout(id=uuid.uuid4())
    with pytest.raises(ConflictError, match="already checked out"):
        await service.checkout_equipment(EquipmentCheckoutCreate(asset_id=asset.id))


@pytest.mark.asyncio
async def test_checkout_rejects_retired_asset(service, repo):
    asset = _asset(condition=EquipmentCondition.RETIRED)
    repo.get_asset.return_value = asset
    with pytest.raises(ConflictError, match="retired"):
        await service.checkout_equipment(EquipmentCheckoutCreate(asset_id=asset.id))


@pytest.mark.asyncio
async def test_checkout_unknown_asset(service, repo):
    repo.get_asset.return_value = None
    with pytest.raises(NotFoundError):
        await service.checkout_equipment(EquipmentCheckoutCreate(asset_id=uuid.uuid4()))


@pytest.mark.asyncio
async def test_checkout_requires_name_or_asset(service, repo):
    with pytest.raises(ValidationFailedError):
        await service.checkout_equipment(EquipmentCheckoutCreate(equipment_name="  "))


@pytest.mark.asyncio
async def test_return_updates_asset_condition(service, repo):
    asset = _asset()
    checkout = EquipmentCheckout(
        id=uuid.uuid4(),
        equipment_name=asset.name,
        asset_id=asset.id,
        checked_out_at=datetime.now(UTC),
        expected_return_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo.get_equipment_checkout.return_value = checkout
    repo.get_asset.return_value = asset
    await service.return_equipment(
        checkout.id, EquipmentReturnRequest(condition=EquipmentCondition.NEEDS_REPAIR)
    )
    assert checkout.returned_at is not None
    assert asset.condition == EquipmentCondition.NEEDS_REPAIR


@pytest.mark.asyncio
async def test_create_asset_rejects_duplicate_serial(service, repo):
    from pawguard.modules.fleet.schemas import EquipmentAssetCreate

    repo.get_asset_by_serial.return_value = _asset(serial_number="SN-1")
    with pytest.raises(ConflictError, match="already registered"):
        await service.create_asset(EquipmentAssetCreate(name="Trap", serial_number="SN-1"))


@pytest.mark.asyncio
async def test_summary_assembles_counts_and_lists(service, repo):
    vehicle = Vehicle(
        id=uuid.uuid4(),
        make_model="Van",
        license_plate="RESCUE-01",
        status=VehicleStatus.ACTIVE,
        insurance_expiry_date=date.today() + timedelta(days=5),
    )
    maintenance = FleetMaintenance(next_due_date=date.today() - timedelta(days=1))
    repo.count_vehicles_by_status.return_value = {"active": 3, "in_maintenance": 1}
    repo.list_insurance_expiring.return_value = [vehicle]
    repo.list_maintenance_due.return_value = [(vehicle, maintenance)]
    repo.count_equipment.return_value = (4, 1)
    repo.count_open_breakdowns.return_value = 2

    summary = await service.get_summary()

    assert summary.total_vehicles == 4
    assert summary.by_status["in_maintenance"] == 1
    assert summary.insurance_expiring[0].license_plate == "RESCUE-01"
    assert summary.maintenance_due[0].due_date == maintenance.next_due_date
    assert (summary.outstanding_equipment, summary.overdue_equipment) == (4, 1)
    assert summary.open_breakdowns == 2
    assert repo.list_insurance_expiring.call_args.args[0] == date.today() + timedelta(days=30)
    assert repo.list_maintenance_due.call_args.args[0] == date.today() + timedelta(days=14)
