"""Unit tests for fleet and medical state machine transition matrices (ITEM 8d).

Covers:
1. VALID_FLEET_TRANSITIONS matrix validation (valid, invalid, terminal states).
2. VALID_MEDICAL_TRANSITIONS matrix validation.
3. FleetService.update_vehicle_status enforces VALID_FLEET_TRANSITIONS.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ValidationFailedError
from pawguard.modules.fleet.models import Vehicle, VehicleStatus
from pawguard.modules.fleet.repository import FleetRepository
from pawguard.modules.fleet.service import VALID_FLEET_TRANSITIONS, FleetService
from pawguard.modules.medical.service import VALID_MEDICAL_TRANSITIONS


def test_fleet_transition_matrix_rules() -> None:
    """Validate all states in VALID_FLEET_TRANSITIONS."""
    assert "in_maintenance" in VALID_FLEET_TRANSITIONS["active"]
    assert "out_of_service" in VALID_FLEET_TRANSITIONS["active"]
    assert "active" in VALID_FLEET_TRANSITIONS["in_maintenance"]
    assert "active" not in VALID_FLEET_TRANSITIONS["out_of_service"]


def test_medical_transition_matrix_rules() -> None:
    """Validate all states in VALID_MEDICAL_TRANSITIONS."""
    assert "approved" in VALID_MEDICAL_TRANSITIONS["pending"]
    assert "denied" in VALID_MEDICAL_TRANSITIONS["pending"]
    assert "completed" in VALID_MEDICAL_TRANSITIONS["approved"]
    assert len(VALID_MEDICAL_TRANSITIONS["completed"]) == 0  # Terminal state


@pytest.mark.asyncio
async def test_fleet_service_rejects_illegal_transition() -> None:
    """FleetService rejects illegal vehicle state transitions (e.g. out_of_service -> active)."""
    mock_repo = AsyncMock(spec=FleetRepository)
    mock_vehicle = MagicMock(spec=Vehicle)
    mock_vehicle.id = uuid.uuid4()
    mock_vehicle.status = VehicleStatus.OUT_OF_SERVICE
    mock_repo.get_vehicle.return_value = mock_vehicle

    service = FleetService(repository=mock_repo)

    with pytest.raises(
        ValidationFailedError, match="Cannot transition vehicle from 'out_of_service' to 'active'"
    ):
        await service.update_vehicle_status(
            vehicle_id=mock_vehicle.id,
            status=VehicleStatus.ACTIVE,
        )


@pytest.mark.asyncio
async def test_fleet_service_allows_legal_transition() -> None:
    """FleetService permits valid vehicle state transitions (active -> in_maintenance)."""
    mock_repo = AsyncMock(spec=FleetRepository)
    mock_vehicle = MagicMock(spec=Vehicle)
    mock_vehicle.id = uuid.uuid4()
    mock_vehicle.status = VehicleStatus.ACTIVE
    mock_repo.get_vehicle.return_value = mock_vehicle
    mock_repo.update_vehicle_status.return_value = mock_vehicle

    service = FleetService(repository=mock_repo)

    result = await service.update_vehicle_status(
        vehicle_id=mock_vehicle.id,
        status=VehicleStatus.IN_MAINTENANCE,
    )
    assert result is not None
    mock_repo.update_vehicle_status.assert_called_once_with(
        mock_vehicle.id, VehicleStatus.IN_MAINTENANCE
    )
