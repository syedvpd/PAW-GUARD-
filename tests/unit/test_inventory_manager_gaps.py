"""Unit tests for Inventory Manager gaps: transitions, expiry clearing, vendors,
stock summary and inter-facility transfers (PRR §2.1, §3.12)."""

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.modules.inventory.models import (
    InventoryItem,
    InventoryItemSupplier,
    ItemCategory,
    MovementType,
    RequisitionOrder,
    RequisitionStatus,
    Supplier,
)
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.schemas import (
    InventoryItemCreate,
    InventoryItemSupplierCreate,
    InventoryItemUpdate,
    InventoryTransferCreate,
    RequisitionOrderCreate,
)
from pawguard.modules.inventory.service import InventoryService


def _item(**overrides: object) -> InventoryItem:
    now = date(2026, 9, 1)
    fields: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "Rabies Vaccine",
        "category": ItemCategory.VACCINE,
        "quantity": 20.0,
        "unit": "dose",
        "reorder_threshold": 5.0,
        "unit_cost": 100.0,
        "facility_id": None,
        "expiry_date": None,
        "created_at": now,
        "updated_at": now,
    }
    fields.update(overrides)
    return InventoryItem(**fields)


def _req(status: RequisitionStatus) -> RequisitionOrder:
    return RequisitionOrder(
        id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        requester_id=uuid.uuid4(),
        quantity=10.0,
        status=status,
    )


@pytest.fixture
def repo() -> AsyncMock:
    mock = AsyncMock(spec=InventoryRepository)
    mock._session = AsyncMock()
    mock.facility_exists.return_value = True
    return mock


@pytest.fixture
def service(repo: AsyncMock) -> InventoryService:
    return InventoryService(repo)


class TestRequisitionTransitions:
    @pytest.mark.asyncio
    async def test_pending_cannot_jump_to_received(self, service, repo):
        repo.get_requisition.return_value = _req(RequisitionStatus.PENDING)
        with pytest.raises(ConflictError):
            await service.update_requisition_status(
                uuid.uuid4(), uuid.uuid4(), RequisitionStatus.RECEIVED
            )
        repo.create_movement.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejected_is_final(self, service, repo):
        repo.get_requisition.return_value = _req(RequisitionStatus.REJECTED)
        with pytest.raises(ConflictError):
            await service.update_requisition_status(
                uuid.uuid4(), uuid.uuid4(), RequisitionStatus.APPROVED
            )

    @pytest.mark.asyncio
    async def test_bulk_received_adds_stock_for_each_requisition(self, service, repo):
        reqs = {
            r.id: r for r in (_req(RequisitionStatus.APPROVED), _req(RequisitionStatus.APPROVED))
        }
        repo.get_requisition.side_effect = lambda rid: reqs.get(rid)
        item = _item(quantity=0.0)
        repo.get_item.return_value = item

        count = await service.bulk_update_requisition_status(
            list(reqs), RequisitionStatus.RECEIVED, user_id=uuid.uuid4()
        )

        assert count == 2
        assert item.quantity == 20.0
        assert repo.create_movement.await_count == 2
        assert all(r.status == RequisitionStatus.RECEIVED for r in reqs.values())

    @pytest.mark.asyncio
    async def test_bulk_rejects_whole_batch_when_one_transition_is_invalid(self, service, repo):
        ok, bad = _req(RequisitionStatus.APPROVED), _req(RequisitionStatus.PENDING)
        repo.get_requisition.side_effect = lambda rid: {ok.id: ok, bad.id: bad}[rid]
        with pytest.raises(ConflictError):
            await service.bulk_update_requisition_status(
                [ok.id, bad.id], RequisitionStatus.RECEIVED, user_id=uuid.uuid4()
            )
        assert ok.status == RequisitionStatus.APPROVED
        repo.create_movement.assert_not_called()


class TestRequisitionVendor:
    @pytest.mark.asyncio
    async def test_inactive_vendor_rejected(self, service, repo):
        repo.get_item.return_value = _item()
        repo.get_supplier_by_id.return_value = Supplier(
            id=uuid.uuid4(), name="Old Co", is_active=False
        )
        with pytest.raises(ConflictError):
            await service.create_requisition(
                uuid.uuid4(),
                RequisitionOrderCreate(item_id=uuid.uuid4(), quantity=5, supplier_id=uuid.uuid4()),
            )

    @pytest.mark.asyncio
    async def test_vendor_stored_on_requisition(self, service, repo):
        supplier_id = uuid.uuid4()
        repo.get_item.return_value = _item()
        repo.get_supplier_by_id.return_value = Supplier(
            id=supplier_id, name="MedSupply", is_active=True
        )
        repo.create_requisition.side_effect = lambda req: req
        req = await service.create_requisition(
            uuid.uuid4(),
            RequisitionOrderCreate(item_id=uuid.uuid4(), quantity=5, supplier_id=supplier_id),
        )
        assert req.supplier_id == supplier_id


class TestItemUpdate:
    @pytest.mark.asyncio
    async def test_explicit_null_clears_expiry_but_not_required_fields(self, service, repo):
        item = _item(expiry_date=date(2027, 1, 1))
        repo.get_item.return_value = item
        repo.update_item.return_value = item

        await service.update_item(
            item.id, InventoryItemUpdate.model_validate({"expiry_date": None, "name": None})
        )

        kwargs = repo.update_item.await_args.kwargs
        assert kwargs == {"expiry_date": None}

    @pytest.mark.asyncio
    async def test_unknown_facility_rejected(self, service, repo):
        repo.facility_exists.return_value = False
        with pytest.raises(NotFoundError):
            await service.create_item(
                InventoryItemCreate(
                    name="Gloves",
                    category=ItemCategory.CONSUMABLE,
                    unit="pair",
                    facility_id=uuid.uuid4(),
                )
            )

    @pytest.mark.asyncio
    async def test_same_name_allowed_in_another_facility(self, service, repo):
        facility = uuid.uuid4()
        repo.get_item_by_name.return_value = None
        repo.create_item.side_effect = lambda item: item
        created = await service.create_item(
            InventoryItemCreate(
                name="Gloves", category=ItemCategory.CONSUMABLE, unit="pair", facility_id=facility
            )
        )
        repo.get_item_by_name.assert_awaited_with("Gloves", facility)
        assert created.facility_id == facility


class TestSummary:
    @pytest.mark.asyncio
    async def test_counts_and_expired(self, service, repo):
        today = date(2026, 9, 19)
        repo.stock_totals.return_value = (10, 4800.0, 120.0)
        repo.list_out_of_stock.return_value = [_item(quantity=0.0)]
        repo.list_low_stock.return_value = [_item(quantity=2.0), _item(quantity=3.0)]
        repo.list_expiring.return_value = [
            _item(expiry_date=date(2026, 9, 1)),
            _item(expiry_date=date(2026, 10, 30)),
        ]

        summary = await service.get_summary(today=today)

        repo.list_expiring.assert_awaited_once_with(date(2026, 11, 18))
        assert summary.total_items == 10
        assert summary.out_of_stock_count == 1
        assert summary.low_stock_count == 2
        assert summary.expiring_count == 2
        assert summary.expired_count == 1
        assert summary.total_stock_value == 4800.0


class TestVendorLinks:
    @pytest.mark.asyncio
    async def test_preferred_link_clears_previous_preferred(self, service, repo):
        item = _item()
        supplier = Supplier(id=uuid.uuid4(), name="MedSupply", is_active=True)
        repo.get_item.return_value = item
        repo.get_supplier_by_id.return_value = supplier
        repo.get_item_supplier.return_value = None

        def create(link: InventoryItemSupplier) -> InventoryItemSupplier:
            link.id = uuid.uuid4()
            link.created_at = date(2026, 9, 19)
            return link

        repo.create_item_supplier.side_effect = create

        result = await service.link_item_supplier(
            item.id,
            InventoryItemSupplierCreate(supplier_id=supplier.id, unit_cost=90, is_preferred=True),
        )

        repo.clear_preferred_supplier.assert_awaited_once_with(item.id)
        assert result.supplier_name == "MedSupply"
        assert result.is_preferred is True

    @pytest.mark.asyncio
    async def test_unlink_missing_is_not_found(self, service, repo):
        repo.delete_item_supplier.return_value = False
        with pytest.raises(NotFoundError):
            await service.unlink_item_supplier(uuid.uuid4(), uuid.uuid4())


class TestTransfers:
    @pytest.mark.asyncio
    async def test_creates_destination_and_records_paired_movements(self, service, repo):
        source = _item(facility_id=uuid.uuid4(), quantity=20.0)
        destination_facility = uuid.uuid4()
        repo.get_item_for_update.return_value = source
        repo.get_item_by_name.return_value = None

        def inserted(item: InventoryItem) -> InventoryItem:
            item.id = uuid.uuid4()
            item.created_at = item.updated_at = date(2026, 9, 19)
            return item

        repo.create_item.side_effect = inserted

        result = await service.transfer_stock(
            uuid.uuid4(),
            InventoryTransferCreate(
                item_id=source.id, to_facility_id=destination_facility, quantity=8
            ),
        )

        assert source.quantity == 12.0
        created = repo.create_item.await_args.args[0]
        assert created.facility_id == destination_facility
        assert created.quantity == 8.0
        movements = [c.args[0] for c in repo.create_movement.await_args_list]
        assert [m.movement_type for m in movements] == [
            MovementType.CHECK_OUT,
            MovementType.CHECK_IN,
        ]
        assert {m.reference_id for m in movements} == {result.transfer_id}
        assert all(m.reference_type == "inventory_transfer" for m in movements)
        refreshed = [c.args[0] for c in repo._session.refresh.await_args_list]
        assert source in refreshed and created in refreshed

    @pytest.mark.asyncio
    async def test_insufficient_stock_blocked(self, service, repo):
        repo.get_item_for_update.return_value = _item(quantity=2.0)
        with pytest.raises(ConflictError):
            await service.transfer_stock(
                uuid.uuid4(),
                InventoryTransferCreate(
                    item_id=uuid.uuid4(), to_facility_id=uuid.uuid4(), quantity=5
                ),
            )
        repo.create_movement.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_facility_rejected(self, service, repo):
        facility = uuid.uuid4()
        repo.get_item_for_update.return_value = _item(facility_id=facility)
        with pytest.raises(ValidationFailedError):
            await service.transfer_stock(
                uuid.uuid4(),
                InventoryTransferCreate(item_id=uuid.uuid4(), to_facility_id=facility, quantity=1),
            )

    @pytest.mark.asyncio
    async def test_unit_mismatch_at_destination_rejected(self, service, repo):
        repo.get_item_for_update.return_value = _item(unit="dose")
        repo.get_item_by_name.return_value = _item(unit="vial")
        with pytest.raises(ConflictError):
            await service.transfer_stock(
                uuid.uuid4(),
                InventoryTransferCreate(
                    item_id=uuid.uuid4(), to_facility_id=uuid.uuid4(), quantity=1
                ),
            )
