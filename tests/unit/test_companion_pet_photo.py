"""Unit tests for companion pet photo upload, storage integration, and response enrichment."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams
from pawguard.modules.auth.dependencies import CurrentUser
from pawguard.modules.companion_pet.models import CompanionPet
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.service import CompanionPetService
from pawguard.modules.storage.service import StorageService


@pytest.fixture
def mock_storage():
    storage = AsyncMock(spec=StorageService)
    storage.get_download_url_for_object = AsyncMock(
        return_value="https://s3.aws.com/signed-pet-photo.jpg"
    )
    storage.request_upload_url = AsyncMock()
    storage.confirm_upload = AsyncMock()
    return storage


@pytest.fixture
def mock_repo():
    repo = AsyncMock(spec=CompanionPetRepository)
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def companion_service(mock_repo, mock_storage):
    db_mock = AsyncMock()
    return CompanionPetService(mock_repo, db_mock, storage=mock_storage)


@pytest.mark.asyncio
async def test_enrich_pet_response_includes_photo_url(companion_service, mock_storage):
    pet_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    pet = CompanionPet(
        id=pet_id,
        owner_id=owner_id,
        name="Rex",
        species="dog",
        breed="German Shepherd",
        is_scan_enabled=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Mock get_pet_photo_url on service
    companion_service.get_pet_photo_url = AsyncMock(
        return_value="https://s3.aws.com/signed-pet-photo.jpg"
    )

    enriched = await companion_service.enrich_pet_response(pet)
    assert enriched.id == pet_id
    assert enriched.name == "Rex"
    assert enriched.photo_url == "https://s3.aws.com/signed-pet-photo.jpg"
    assert enriched.photo_urls == ["https://s3.aws.com/signed-pet-photo.jpg"]


@pytest.mark.asyncio
async def test_list_pets_enriches_all_returned_pets(companion_service, mock_repo):
    pet1 = CompanionPet(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        name="Milo",
        species="cat",
        is_scan_enabled=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_repo.list_pets.return_value = ([pet1], 1)
    companion_service.get_pet_photo_url = AsyncMock(return_value="https://s3.aws.com/milo.jpg")

    from pawguard.modules.auth.models import User

    user = User(
        id=pet1.owner_id,
        email="owner@test.com",
        full_name="Pet Owner",
        hashed_password="hash",
        is_active=True,
    )
    caller = CurrentUser(
        user=user,
        claims={"sub": str(pet1.owner_id), "roles": ["user"]},
        db=AsyncMock(),
        redis=AsyncMock(),
    )
    page = PageParams(page=1, page_size=10)
    sort = SortParams(sort_by="created_at", sort_order="desc")

    result = await companion_service.list_pets(page, sort, caller)
    assert len(result.data) == 1
    assert result.data[0].photo_url == "https://s3.aws.com/milo.jpg"
