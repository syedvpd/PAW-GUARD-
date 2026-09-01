"""Unit tests for veterinarian dog vaccination and medication reminders."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.medical.models import Prescription, VaccinationRecord
from pawguard.modules.medical.repository import MedicalRepository
from pawguard.modules.medical.service import MedicalService


@pytest.fixture
def mock_repo():
    repo = AsyncMock(spec=MedicalRepository)
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def mock_dog_repo():
    repo = AsyncMock(spec=DogRepository)
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def medical_service(mock_repo, mock_dog_repo):
    return MedicalService(mock_repo, mock_dog_repo)


@pytest.mark.asyncio
async def test_get_dog_reminders_aggregates_upcoming_and_overdue(
    medical_service, mock_repo, mock_dog_repo
):
    dog_id = uuid.uuid4()
    dog = DogProfile(
        id=dog_id,
        registration_number="DOG-REM-01",
        name="Charlie",
        breed="Golden Retriever",
        status=DogStatus.SHELTER,
        is_adoptable=True,
    )
    mock_dog_repo.get_by_id.return_value = dog

    today = datetime.now(UTC)
    # 1 overdue vax, 1 upcoming vax
    vax1 = VaccinationRecord(
        id=uuid.uuid4(),
        dog_id=dog_id,
        administered_by=uuid.uuid4(),
        vaccine_name="Rabies",
        administered_at=today - timedelta(days=380),
        next_due_at=today - timedelta(days=15),
        lot_number="LOT-001",
    )
    vax2 = VaccinationRecord(
        id=uuid.uuid4(),
        dog_id=dog_id,
        administered_by=uuid.uuid4(),
        vaccine_name="DHPP",
        administered_at=today - timedelta(days=300),
        next_due_at=today + timedelta(days=65),
        lot_number="LOT-002",
    )
    mock_repo.get_vaccinations_by_dog.return_value = [vax1, vax2]

    # 1 active prescription
    rx1 = Prescription(
        id=uuid.uuid4(),
        dog_id=dog_id,
        vet_id=uuid.uuid4(),
        drug_name="Amoxicillin",
        dosage="250mg",
        route="Oral",
        is_active=True,
        start_at=today - timedelta(days=3),
        end_at=today + timedelta(days=7),
    )
    mock_repo.get_prescriptions_by_dog.return_value = [rx1]
    mock_repo.get_treatments_by_dog.return_value = []

    res = await medical_service.get_dog_reminders(dog_id)
    assert res.dog_id == dog_id
    assert res.dog_name == "Charlie"
    assert res.total_reminders == 3
    assert res.overdue_count == 1
    assert res.upcoming_count == 1
    assert len(res.vaccinations) == 2
    assert len(res.medications) == 1
