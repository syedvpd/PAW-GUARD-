"""Unit tests for InventoryMovement reference integrity and validation (ITEM 4).

Covers:
1. Movement with a non-existent reference_id raises ValidationFailedError.
2. Movement with mismatched reference pair (reference_id without reference_type) raises ValidationFailedError.
3. Movement with invalid/unmapped reference_type raises ValidationFailedError.
4. Movement with existing referenced entity succeeds.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ValidationFailedError
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.inventory.models import InventoryItem, MovementType
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.schemas import InventoryMovementCreate
from pawguard.modules.inventory.service import InventoryService


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_repo(mock_session: AsyncMock) -> InventoryRepository:
    repo = AsyncMock(spec=InventoryRepository)
    repo._session = mock_session
    mock_item = MagicMock(spec=InventoryItem)
    mock_item.id = uuid.uuid4()
    mock_item.name = "Amoxicillin 500mg"
    mock_item.quantity = 100.0
    mock_item.unit = "tablets"
    mock_item.expiry_date = None
    mock_item.reorder_threshold = 10.0
    repo.get_item_for_update.return_value = mock_item
    repo.get_item.return_value = mock_item
    return repo


@pytest.fixture
def inventory_service(mock_repo: InventoryRepository) -> InventoryService:
    return InventoryService(repository=mock_repo)


@pytest.mark.asyncio
async def test_record_movement_rejects_non_existent_reference_id(
    inventory_service: InventoryService, mock_session: AsyncMock
) -> None:
    """Movement with a non-existent reference_id must be rejected."""
    mock_session.get.return_value = None  # Entity not found in DB

    payload = InventoryMovementCreate(
        item_id=uuid.uuid4(),
        movement_type=MovementType.CONSUMPTION,
        quantity=5.0,
        reference_type="dog",
        reference_id=uuid.uuid4(),
    )

    with pytest.raises(ValidationFailedError, match="does not exist"):
        await inventory_service.record_movement(
            user_id=uuid.uuid4(),
            payload=payload,
        )


@pytest.mark.asyncio
async def test_record_movement_rejects_mismatched_reference_pair(
    inventory_service: InventoryService,
) -> None:
    """Movement with reference_id but no reference_type (or vice versa) is rejected."""
    payload_id_only = InventoryMovementCreate(
        item_id=uuid.uuid4(),
        movement_type=MovementType.CHECK_OUT,
        quantity=2.0,
        reference_id=uuid.uuid4(),
        reference_type=None,
    )

    with pytest.raises(ValidationFailedError, match="Both reference_type and reference_id"):
        await inventory_service.record_movement(
            user_id=uuid.uuid4(),
            payload=payload_id_only,
        )


@pytest.mark.asyncio
async def test_record_movement_rejects_invalid_reference_type(
    inventory_service: InventoryService,
) -> None:
    """Movement with unmapped reference_type is rejected."""
    payload = InventoryMovementCreate(
        item_id=uuid.uuid4(),
        movement_type=MovementType.CHECK_OUT,
        quantity=1.0,
        reference_type="unknown_table_xyz",
        reference_id=uuid.uuid4(),
    )

    with pytest.raises(ValidationFailedError, match="Invalid reference_type"):
        await inventory_service.record_movement(
            user_id=uuid.uuid4(),
            payload=payload,
        )


@pytest.mark.asyncio
async def test_record_movement_rejects_type_without_id(
    inventory_service: InventoryService,
) -> None:
    """Movement with reference_type but no reference_id is rejected."""
    payload = InventoryMovementCreate(
        item_id=uuid.uuid4(),
        movement_type=MovementType.CHECK_OUT,
        quantity=2.0,
        reference_type="dog",
        reference_id=None,
    )

    with pytest.raises(ValidationFailedError, match="Both reference_type and reference_id"):
        await inventory_service.record_movement(
            user_id=uuid.uuid4(),
            payload=payload,
        )


@pytest.mark.asyncio
async def test_record_movement_rejects_soft_deleted_reference_entity(
    inventory_service: InventoryService, mock_session: AsyncMock
) -> None:
    """Movement referencing a soft-deleted entity is rejected."""
    from datetime import UTC, datetime

    mock_dog = MagicMock(spec=DogProfile)
    mock_dog.id = uuid.uuid4()
    mock_dog.deleted_at = datetime.now(UTC)
    mock_session.get.return_value = mock_dog

    payload = InventoryMovementCreate(
        item_id=uuid.uuid4(),
        movement_type=MovementType.CONSUMPTION,
        quantity=3.0,
        reference_type="dog",
        reference_id=mock_dog.id,
    )

    with pytest.raises(ValidationFailedError, match="soft-deleted"):
        await inventory_service.record_movement(
            user_id=uuid.uuid4(),
            payload=payload,
        )


@pytest.mark.asyncio
async def test_record_movement_succeeds_with_null_reference_pair(
    inventory_service: InventoryService, mock_repo: InventoryRepository
) -> None:
    """Movement with both reference_type and reference_id as None succeeds (standard movement)."""
    payload = InventoryMovementCreate(
        item_id=uuid.uuid4(),
        movement_type=MovementType.CHECK_IN,
        quantity=10.0,
        reference_type=None,
        reference_id=None,
    )

    result = await inventory_service.record_movement(
        user_id=uuid.uuid4(),
        payload=payload,
    )

    assert result is not None
    assert result.reference_type is None
    assert result.reference_id is None
    mock_repo.create_movement.assert_called_once()


@pytest.mark.asyncio
async def test_record_movement_succeeds_with_valid_reference(
    inventory_service: InventoryService, mock_session: AsyncMock, mock_repo: InventoryRepository
) -> None:
    """Movement with valid referenced entity succeeds."""
    mock_dog = MagicMock(spec=DogProfile)
    mock_dog.id = uuid.uuid4()
    mock_dog.deleted_at = None
    mock_session.get.return_value = mock_dog

    payload = InventoryMovementCreate(
        item_id=uuid.uuid4(),
        movement_type=MovementType.CONSUMPTION,
        quantity=5.0,
        reference_type="dog",
        reference_id=mock_dog.id,
    )

    result = await inventory_service.record_movement(
        user_id=uuid.uuid4(),
        payload=payload,
    )

    assert result is not None
    assert result.reference_type == "dog"
    assert result.reference_id == mock_dog.id
    mock_repo.create_movement.assert_called_once()
