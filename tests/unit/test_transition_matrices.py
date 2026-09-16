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


@pytest.mark.asyncio
async def test_medical_service_enforces_transition_matrix() -> None:
    """MedicalService.update_clearance_status strictly enforces VALID_MEDICAL_TRANSITIONS."""
    from pawguard.modules.dog.repository import DogRepository
    from pawguard.modules.medical.models import MedicalClearance
    from pawguard.modules.medical.repository import MedicalRepository
    from pawguard.modules.medical.service import MedicalService

    mock_repo = AsyncMock(spec=MedicalRepository)
    mock_repo._session = AsyncMock()
    mock_dog_repo = AsyncMock(spec=DogRepository)

    service = MedicalService(repository=mock_repo, dog_repo=mock_dog_repo)

    clearance = MedicalClearance(
        id=uuid.uuid4(),
        dog_id=uuid.uuid4(),
        authorized_by_id=uuid.uuid4(),
        clearance_type="adoption_surgery",
        status="pending",
    )
    mock_repo.get_clearance_by_id.return_value = clearance
    mock_dog_repo.get_by_id.return_value = MagicMock()

    # pending -> approved: PASS
    res = await service.update_clearance_status(clearance.id, "approved")
    assert res.status == "approved"

    # approved -> completed: PASS
    res = await service.update_clearance_status(clearance.id, "completed")
    assert res.status == "completed"

    # completed -> anything: FAIL (terminal)
    with pytest.raises(
        ValidationFailedError,
        match="Invalid medical status transition from 'completed' to 'pending'",
    ):
        await service.update_clearance_status(clearance.id, "pending")

    with pytest.raises(ValidationFailedError, match="terminal state"):
        await service.update_clearance_status(clearance.id, "approved")

    # pending -> completed: FAIL
    clearance.status = "pending"
    with pytest.raises(
        ValidationFailedError,
        match="Invalid medical status transition from 'pending' to 'completed'",
    ):
        await service.update_clearance_status(clearance.id, "completed")

    # approved -> pending: FAIL
    clearance.status = "approved"
    with pytest.raises(
        ValidationFailedError,
        match="Invalid medical status transition from 'approved' to 'pending'",
    ):
        await service.update_clearance_status(clearance.id, "pending")

    # cancelled -> anything: FAIL (terminal)
    clearance.status = "cancelled"
    with pytest.raises(
        ValidationFailedError,
        match="Invalid medical status transition from 'cancelled' to 'approved'",
    ):
        await service.update_clearance_status(clearance.id, "approved")
