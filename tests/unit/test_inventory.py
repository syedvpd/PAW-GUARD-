"""Unit tests for InventoryService with mocked repository."""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.inventory.models import (
    InventoryItem,
    ItemCategory,
    MovementType,
    RequisitionOrder,
    RequisitionStatus,
)
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.schemas import (
    InventoryItemCreate,
    InventoryMovementCreate,
    RequisitionOrderCreate,
)
from pawguard.modules.inventory.service import InventoryService
from pawguard.services.audit_service import AuditService


class TestInventoryService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=InventoryRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return InventoryService(mock_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_create_item(self, service, mock_repo):
        mock_repo.get_item_by_name.return_value = None
        item_id = uuid.uuid4()
        mock_repo.create_item.return_value = InventoryItem(
            id=item_id,
            name="Bandages",
            category=ItemCategory.CONSUMABLE,
            quantity=100.0,
            unit="pack",
            reorder_threshold=10.0,
        )
        payload = InventoryItemCreate(
            name="Bandages",
            category=ItemCategory.CONSUMABLE,
            quantity=100.0,
            unit="pack",
        )
        result = await service.create_item(payload, actor_id=uuid.uuid4())
        assert result.name == "Bandages"

    @pytest.mark.asyncio
    async def test_create_item_duplicate(self, service, mock_repo):
        mock_repo.get_item_by_name.return_value = InventoryItem(
            id=uuid.uuid4(),
            name="Bandages",
            category=ItemCategory.CONSUMABLE,
            quantity=10.0,
            unit="pack",
            reorder_threshold=5.0,
        )
        payload = InventoryItemCreate(
            name="Bandages",
            category=ItemCategory.CONSUMABLE,
            quantity=10.0,
            unit="pack",
        )
        with pytest.raises(ConflictError, match="already registered"):
            await service.create_item(payload)

    @pytest.mark.asyncio
    async def test_record_movement_check_in(self, service, mock_repo):
        item_id = uuid.uuid4()
        item = InventoryItem(
            id=item_id,
            name="Food",
            category=ItemCategory.FOOD,
            quantity=50.0,
            unit="kg",
            reorder_threshold=10.0,
        )
        mock_repo.get_item.return_value = item
        uuid.uuid4()
        mock_repo.create_movement.return_value = None
        payload = InventoryMovementCreate(
            item_id=item_id,
            movement_type=MovementType.CHECK_IN,
            quantity=20.0,
        )
        await service.record_movement(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert item.quantity == 70.0

    @pytest.mark.asyncio
    async def test_record_movement_check_out(self, service, mock_repo):
        item_id = uuid.uuid4()
        item = InventoryItem(
            id=item_id,
            name="Food",
            category=ItemCategory.FOOD,
            quantity=50.0,
            unit="kg",
            reorder_threshold=10.0,
        )
        mock_repo.get_item.return_value = item
        payload = InventoryMovementCreate(
            item_id=item_id,
            movement_type=MovementType.CHECK_OUT,
            quantity=10.0,
        )
        await service.record_movement(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert item.quantity == 40.0

    @pytest.mark.asyncio
    async def test_record_movement_check_out_expired(self, service, mock_repo):
        from datetime import date, timedelta

        item_id = uuid.uuid4()
        item = InventoryItem(
            id=item_id,
            name="Expired Meds",
            category=ItemCategory.PHARMACEUTICAL,
            quantity=50.0,
            unit="vial",
            reorder_threshold=5.0,
            expiry_date=date.today() - timedelta(days=5),
        )
        mock_repo.get_item.return_value = item
        payload = InventoryMovementCreate(
            item_id=item_id,
            movement_type=MovementType.CHECK_OUT,
            quantity=10.0,
        )
        with pytest.raises(ConflictError, match="Cannot check out expired inventory item"):
            await service.record_movement(uuid.uuid4(), payload, actor_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_record_movement_adjustment(self, service, mock_repo):
        item_id = uuid.uuid4()
        item = InventoryItem(
            id=item_id,
            name="Medicine",
            category=ItemCategory.PHARMACEUTICAL,
            quantity=50.0,
            unit="vial",
            reorder_threshold=5.0,
        )
        mock_repo.get_item.return_value = item
        payload = InventoryMovementCreate(
            item_id=item_id,
            movement_type=MovementType.ADJUSTMENT,
            quantity=30.0,
        )
        await service.record_movement(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert item.quantity == 30.0

    @pytest.mark.asyncio
    async def test_record_movement_insufficient_stock(self, service, mock_repo):
        item_id = uuid.uuid4()
        item = InventoryItem(
            id=item_id,
            name="Food",
            category=ItemCategory.FOOD,
            quantity=5.0,
            unit="kg",
            reorder_threshold=10.0,
        )
        mock_repo.get_item.return_value = item
        payload = InventoryMovementCreate(
            item_id=item_id,
            movement_type=MovementType.CHECK_OUT,
            quantity=10.0,
        )
        with pytest.raises(ConflictError, match="Insufficient stock"):
            await service.record_movement(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_record_movement_item_not_found(self, service, mock_repo):
        mock_repo.get_item.return_value = None
        payload = InventoryMovementCreate(
            item_id=uuid.uuid4(),
            movement_type=MovementType.CHECK_IN,
            quantity=1.0,
        )
        with pytest.raises(NotFoundError):
            await service.record_movement(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_create_requisition(self, service, mock_repo):
        item_id = uuid.uuid4()
        mock_repo.get_item.return_value = InventoryItem(
            id=item_id,
            name="Food",
            category=ItemCategory.FOOD,
            quantity=0.0,
            unit="kg",
            reorder_threshold=10.0,
        )
        req_id = uuid.uuid4()
        mock_repo.create_requisition.return_value = RequisitionOrder(
            id=req_id,
            item_id=item_id,
            requester_id=uuid.uuid4(),
            quantity=50.0,
            status=RequisitionStatus.PENDING,
        )
        payload = RequisitionOrderCreate(item_id=item_id, quantity=50.0)
        result = await service.create_requisition(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.status == RequisitionStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_requisition_item_not_found(self, service, mock_repo):
        mock_repo.get_item.return_value = None
        payload = RequisitionOrderCreate(item_id=uuid.uuid4(), quantity=10.0)
        with pytest.raises(NotFoundError):
            await service.create_requisition(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_update_requisition_status_received(self, service, mock_repo):
        req_id = uuid.uuid4()
        item_id = uuid.uuid4()
        req = RequisitionOrder(
            id=req_id,
            item_id=item_id,
            requester_id=uuid.uuid4(),
            quantity=50.0,
            status=RequisitionStatus.APPROVED,
        )
        mock_repo.get_requisition.return_value = req
        item = InventoryItem(
            id=item_id,
            name="Food",
            category=ItemCategory.FOOD,
            quantity=100.0,
            unit="kg",
            reorder_threshold=10.0,
        )
        mock_repo.get_item.return_value = item
        mock_repo.create_movement.return_value = None
        result = await service.update_requisition_status(
            uuid.uuid4(),
            req_id,
            RequisitionStatus.RECEIVED,
            actor_id=uuid.uuid4(),
        )
        assert result.status == RequisitionStatus.RECEIVED
        assert item.quantity == 150.0

    @pytest.mark.asyncio
    async def test_update_requisition_status_already_received(self, service, mock_repo):
        req_id = uuid.uuid4()
        mock_repo.get_requisition.return_value = RequisitionOrder(
            id=req_id,
            item_id=uuid.uuid4(),
            requester_id=uuid.uuid4(),
            quantity=10.0,
            status=RequisitionStatus.RECEIVED,
        )
        with pytest.raises(ConflictError, match="already marked as received"):
            await service.update_requisition_status(
                uuid.uuid4(), req_id, RequisitionStatus.RECEIVED
            )

    @pytest.mark.asyncio
    async def test_get_item(self, service, mock_repo):
        item_id = uuid.uuid4()
        mock_repo.get_item.return_value = InventoryItem(
            id=item_id,
            name="Food",
            category=ItemCategory.FOOD,
            quantity=10.0,
            unit="kg",
            reorder_threshold=5.0,
        )
        result = await service.get_item(item_id)
        assert result.id == item_id

    @pytest.mark.asyncio
    async def test_get_item_not_found(self, service, mock_repo):
        mock_repo.get_item.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_item(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_items_paginated(self, service, mock_repo):
        item = InventoryItem(
            id=uuid.uuid4(),
            name="Food",
            category=ItemCategory.FOOD,
            quantity=10.0,
            unit="kg",
            reorder_threshold=5.0,
        )
        mock_repo.list_items_paginated.return_value = ([item], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_items_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_item(self, service, mock_repo):
        item_id = uuid.uuid4()
        mock_repo.soft_delete_item.return_value = True
        await service.soft_delete_item(item_id, actor_id=uuid.uuid4())
        mock_repo.soft_delete_item.assert_called_once_with(item_id)

    @pytest.mark.asyncio
    async def test_soft_delete_item_not_found(self, service, mock_repo):
        mock_repo.soft_delete_item.return_value = False
        with pytest.raises(NotFoundError):
            await service.soft_delete_item(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_item_with_unit_cost(self, service, mock_repo):
        mock_repo.get_item_by_name.return_value = None
        item_id = uuid.uuid4()
        mock_repo.create_item.return_value = InventoryItem(
            id=item_id,
            name="Bandages",
            category=ItemCategory.CONSUMABLE,
            quantity=100.0,
            unit="pack",
            reorder_threshold=10.0,
            unit_cost=5.99,
        )
        payload = InventoryItemCreate(
            name="Bandages",
            category=ItemCategory.CONSUMABLE,
            quantity=100.0,
            unit="pack",
            unit_cost=5.99,
        )
        result = await service.create_item(payload, actor_id=uuid.uuid4())
        assert result.unit_cost == 5.99

    @pytest.mark.asyncio
    async def test_record_movement_with_reference(self, service, mock_repo):
        item_id = uuid.uuid4()
        item = InventoryItem(
            id=item_id,
            name="Food",
            category=ItemCategory.FOOD,
            quantity=50.0,
            unit="kg",
            reorder_threshold=10.0,
        )
        mock_repo.get_item.return_value = item
        mock_repo.create_movement.return_value = None
        ref_id = uuid.uuid4()
        payload = InventoryMovementCreate(
            item_id=item_id,
            movement_type=MovementType.CHECK_IN,
            quantity=20.0,
            reference_type="foster_supply",
            reference_id=ref_id,
        )
        result = await service.record_movement(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.reference_type == "foster_supply"
        assert result.reference_id == ref_id

    def test_inventory_item_create_frontend_compatibility(self):
        # Frontend might send 'Consumables', 'initial_quantity', 'unit_type', or empty expiry_date string
        raw_data = {
            "name": "induja",
            "category": "Consumables",
            "unit_type": "vials",
            "initial_quantity": 50,
            "reorder_threshold": 10,
            "unit_cost": 5,
            "expiry_date": "",
        }
        item = InventoryItemCreate.model_validate(raw_data)
        assert item.name == "induja"
        assert item.category == ItemCategory.CONSUMABLE
        assert item.unit == "vials"
        assert item.quantity == 50.0
        assert item.expiry_date is None

    @pytest.mark.asyncio
    async def test_router_create_item_success(self):
        from unittest.mock import MagicMock

        from pawguard.modules.auth.dependencies import CurrentUser
        from pawguard.modules.inventory.router import create_item

        service = AsyncMock(spec=InventoryService)
        item_id = uuid.uuid4()
        from datetime import datetime

        now = datetime.now(UTC)
        service.create_item.return_value = InventoryItem(
            id=item_id,
            name="induja",
            category=ItemCategory.CONSUMABLE,
            quantity=50.0,
            unit="vials",
            reorder_threshold=10.0,
            unit_cost=5.0,
            created_at=now,
            updated_at=now,
        )

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        current_user = CurrentUser(
            user=mock_user,
            claims=MagicMock(),
            db=MagicMock(),
            redis=MagicMock(),
        )
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        payload = InventoryItemCreate(
            name="induja",
            category=ItemCategory.CONSUMABLE,
            unit="vials",
            quantity=50.0,
            reorder_threshold=10.0,
            unit_cost=5.0,
        )
        response = await create_item(
            payload=payload,
            request=mock_request,
            current_user=current_user,
            service=service,
        )
        assert response.data.id == item_id
        assert response.data.name == "induja"
        assert response.message == "Inventory item created."

    @pytest.mark.asyncio
    async def test_router_update_requisition_status_workflow8_admin_required(self):
        from unittest.mock import MagicMock

        from pawguard.modules.auth.dependencies import CurrentUser
        from pawguard.modules.inventory.router import update_requisition_status
        from pawguard.modules.inventory.schemas import RequisitionStatusUpdate

        service = AsyncMock(spec=InventoryService)
        req_id = uuid.uuid4()

        # Regular user without system:admin
        regular_user = MagicMock()
        regular_user.id = uuid.uuid4()
        regular_user.roles = []
        regular_current_user = CurrentUser(
            user=regular_user,
            claims=MagicMock(),
            db=MagicMock(),
            redis=MagicMock(),
        )

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        payload = RequisitionStatusUpdate(status=RequisitionStatus.APPROVED)
        with pytest.raises(ForbiddenError, match="administrator privileges"):
            await update_requisition_status(
                req_id=req_id,
                payload=payload,
                request=mock_request,
                current_user=regular_current_user,
                service=service,
            )
