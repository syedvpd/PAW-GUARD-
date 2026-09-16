"""Unit tests for BulkOperationMixin, bulk_set_column, and apply_equality_filters (ITEM 8a, 8b, 8c).

Covers:
1. bulk_set_column executes parameterized updates with synchronize_session.
2. BulkOperationMixin invokes before and after hooks and updates status.
3. apply_equality_filters dynamically applies existing model attributes to queries.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from pawguard.core.bulk import BulkOperationMixin, bulk_set_column
from pawguard.core.search import apply_equality_filters
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.fleet.models import Vehicle, VehicleStatus


class DummyBulkService(BulkOperationMixin):
    pass


@pytest.mark.asyncio
async def test_bulk_set_column_updates_records() -> None:
    """bulk_set_column executes update query on given ids and flushes session."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 3
    mock_session.execute.return_value = mock_result

    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    count = await bulk_set_column(
        session=mock_session,
        model=DogProfile,
        ids=ids,
        status=DogStatus.ADOPTED,
    )

    assert count == 3
    mock_session.execute.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_bulk_set_column_empty_ids_returns_zero() -> None:
    """bulk_set_column with empty list returns 0 without executing queries."""
    mock_session = AsyncMock()
    count = await bulk_set_column(
        session=mock_session,
        model=DogProfile,
        ids=[],
        status=DogStatus.ADOPTED,
    )
    assert count == 0
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_operation_mixin_triggers_hooks() -> None:
    """BulkOperationMixin triggers before and after async hooks."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 2
    mock_session.execute.return_value = mock_result

    service = DummyBulkService()
    before_called = False
    after_called = False

    async def before_hook(ids, status):
        nonlocal before_called
        before_called = True

    async def after_hook(ids, status):
        nonlocal after_called
        after_called = True

    ids = [uuid.uuid4(), uuid.uuid4()]
    count = await service.bulk_update_status(
        session=mock_session,
        model=Vehicle,
        ids=ids,
        new_status=VehicleStatus.IN_MAINTENANCE.value,
        before_hook=before_hook,
        after_hook=after_hook,
    )

    assert count == 2
    assert before_called is True
    assert after_called is True


def test_apply_equality_filters() -> None:
    """apply_equality_filters applies matching model attribute filters and ignores None."""
    stmt = select(DogProfile)
    filtered = apply_equality_filters(
        stmt,
        DogProfile,
        breed="Indie",
        gender="male",
        non_existent_column="ignore_me",
        microchip_number=None,
    )
    compiled = str(filtered)
    assert "dog_profiles.breed =" in compiled
    assert "dog_profiles.gender =" in compiled
    assert "non_existent_column" not in compiled
