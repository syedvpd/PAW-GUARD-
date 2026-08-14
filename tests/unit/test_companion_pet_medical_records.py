import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from pawguard.modules.companion_pet.models import CompanionPet, PetMedicalRecord
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.schemas import MedicalRecordUpdate
from pawguard.modules.companion_pet.service import CompanionPetService
from pawguard.modules.storage.models import StoredFile
from pawguard.modules.storage.schemas import DownloadUrlResponse
from pawguard.modules.storage.service import StorageService


def _current_user(user_id: uuid.UUID, *roles: str) -> Any:
    return SimpleNamespace(
        id=user_id,
        user=SimpleNamespace(id=user_id),
        claims=SimpleNamespace(roles=list(roles)),
    )


def _pet(owner_id: uuid.UUID) -> CompanionPet:
    return CompanionPet(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name="Milo",
        species="dog",
        is_scan_enabled=True,
    )


@pytest.mark.asyncio
async def test_get_medical_record_success_owner() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    record = PetMedicalRecord(
        id=uuid.uuid4(),
        pet_id=pet.id,
        clinic_id=None,
        authored_by_id=owner_id,
        record_type="Checkup",
        title="Routine Checkup",
        notes="All good",
        occurred_at=datetime.now(UTC),
    )

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.get_medical_record.return_value = record
    service = CompanionPetService(repo, AsyncMock())

    result = await service.get_medical_record(record.id, _current_user(owner_id))
    assert result.id == record.id
    assert result.title == "Routine Checkup"


@pytest.mark.asyncio
async def test_get_medical_record_forbidden_unrelated_user() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    record = PetMedicalRecord(
        id=uuid.uuid4(),
        pet_id=pet.id,
        clinic_id=None,
        authored_by_id=owner_id,
        record_type="Checkup",
        title="Routine Checkup",
    )

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.get_medical_record.return_value = record
    repo.has_pet_clinic_access.return_value = False
    service = CompanionPetService(repo, AsyncMock())

    with pytest.raises(ForbiddenError):
        await service.get_medical_record(record.id, _current_user(uuid.uuid4()))


@pytest.mark.asyncio
async def test_get_medical_record_not_found() -> None:
    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_medical_record.return_value = None
    service = CompanionPetService(repo, AsyncMock())

    with pytest.raises(NotFoundError):
        await service.get_medical_record(uuid.uuid4(), _current_user(uuid.uuid4()))


@pytest.mark.asyncio
async def test_update_medical_record_success_owner() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    record = PetMedicalRecord(
        id=uuid.uuid4(),
        pet_id=pet.id,
        clinic_id=None,
        authored_by_id=owner_id,
        record_type="Checkup",
        title="Routine Checkup",
    )

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.get_medical_record.return_value = record
    session = AsyncMock()
    service = CompanionPetService(repo, session)

    payload = MedicalRecordUpdate(title="Annual Checkup", notes="Weight looks fine")
    result = await service.update_medical_record(record.id, payload, _current_user(owner_id))

    assert result.title == "Annual Checkup"
    assert result.notes == "Weight looks fine"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_medical_record_clinic_validation() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    record = PetMedicalRecord(
        id=uuid.uuid4(),
        pet_id=pet.id,
        clinic_id=None,
        authored_by_id=owner_id,
        record_type="Checkup",
        title="Routine Checkup",
    )

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.get_medical_record.return_value = record
    repo.get_clinic.return_value = None  # clinic does not exist
    service = CompanionPetService(repo, AsyncMock())

    payload = MedicalRecordUpdate(clinic_id=uuid.uuid4())
    with pytest.raises(NotFoundError):
        await service.update_medical_record(record.id, payload, _current_user(owner_id))


@pytest.mark.asyncio
async def test_update_medical_record_file_validation_not_owned() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    record = PetMedicalRecord(
        id=uuid.uuid4(),
        pet_id=pet.id,
        clinic_id=None,
        authored_by_id=owner_id,
        record_type="Checkup",
        title="Routine Checkup",
    )

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.get_medical_record.return_value = record
    
    stored_file = StoredFile(
        id=uuid.uuid4(),
        entity_type="companion_pet",
        entity_id=uuid.uuid4(),  # belongs to a different pet
    )
    storage = AsyncMock(spec=StorageService)
    storage.get_file.return_value = stored_file
    
    service = CompanionPetService(repo, AsyncMock(), storage=storage)

    payload = MedicalRecordUpdate(stored_file_id=stored_file.id)
    with pytest.raises(ForbiddenError):
        await service.update_medical_record(record.id, payload, _current_user(owner_id))


@pytest.mark.asyncio
async def test_get_medical_file_download_url_success() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    stored_file = StoredFile(
        id=uuid.uuid4(),
        entity_type="companion_pet",
        entity_id=pet.id,
        object_key="medical/test.pdf",
    )

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    
    storage = AsyncMock(spec=StorageService)
    storage.get_file.return_value = stored_file
    storage.get_download_url.return_value = DownloadUrlResponse(
        download_url="https://s3.amazonaws.com/test",
        object_key=stored_file.object_key,
        file_id=stored_file.id,
    )

    service = CompanionPetService(repo, AsyncMock(), storage=storage)
    result = await service.get_medical_file_download_url(stored_file.id, _current_user(owner_id))

    assert result.download_url == "https://s3.amazonaws.com/test"
    storage.get_download_url.assert_awaited_once_with(stored_file.id)


@pytest.mark.asyncio
async def test_get_medical_file_download_url_forbidden() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    stored_file = StoredFile(
        id=uuid.uuid4(),
        entity_type="dog",  # not companion pet
        entity_id=uuid.uuid4(),
    )

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    
    storage = AsyncMock(spec=StorageService)
    storage.get_file.return_value = stored_file

    service = CompanionPetService(repo, AsyncMock(), storage=storage)
    with pytest.raises(ForbiddenError):
        await service.get_medical_file_download_url(stored_file.id, _current_user(owner_id))
