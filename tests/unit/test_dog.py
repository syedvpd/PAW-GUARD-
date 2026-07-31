"""Unit tests for DogService with mocked DogRepository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import DogProfileCreate, DogProfileUpdate
from pawguard.modules.dog.service import DogService
from pawguard.services.audit_service import AuditService


def _make_dog(**kw):
    now = datetime.now(UTC)
    vals = dict(
        is_spayed_neutered=False, is_quarantine_passed=False,
        created_at=now, updated_at=now,
    )
    vals.update(kw)
    return DogProfile(**vals)


class TestDogService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=DogRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return DogService(mock_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_register_dog(self, service, mock_repo, mock_audit):
        dog_id = uuid.uuid4()
        mock_repo.create.return_value = DogProfile(
            id=dog_id, registration_number="DOG-2026-1234", name="Buddy", breed="Labrador",
            gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        payload = DogProfileCreate(name="Buddy", breed="Labrador", gender="male")
        result = await service.register_dog(payload, actor_id=uuid.uuid4())
        assert result.name == "Buddy"
        assert result.registration_number.startswith("DOG-")

    @pytest.mark.asyncio
    async def test_get_dog_found(self, service, mock_repo):
        dog_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = _make_dog(
            id=dog_id, registration_number="DOG-2026-0001", name="Max", breed="Beagle",
            gender="male", status=DogStatus.SHELTER, is_adoptable=True,
        )
        result = await service.get_dog(dog_id)
        assert result.name == "Max"

    @pytest.mark.asyncio
    async def test_get_dog_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError, match="Dog profile not found"):
            await service.get_dog(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_dog(self, service, mock_repo):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0002", name="Old", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        payload = DogProfileUpdate(name="Updated")
        result = await service.update_dog(dog_id, payload, actor_id=uuid.uuid4())
        assert result.name == "Updated"

    @pytest.mark.asyncio
    async def test_update_dog_cannot_grant_is_adoptable(self, service, mock_repo):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0002", name="Old", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        payload = DogProfileUpdate(is_adoptable=True)
        with pytest.raises(ForbiddenError, match="medical clearance"):
            await service.update_dog(dog_id, payload, actor_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_register_dog_ignores_is_adoptable_payload(self, service, mock_repo, mock_audit):
        dog_id = uuid.uuid4()
        mock_repo.create.return_value = DogProfile(
            id=dog_id, registration_number="DOG-2026-1234", name="Buddy", breed="Labrador",
            gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        payload = DogProfileCreate(name="Buddy", breed="Labrador", gender="male", is_adoptable=True)
        await service.register_dog(payload, actor_id=uuid.uuid4())
        created_dog = mock_repo.create.call_args[0][0]
        assert created_dog.is_adoptable is False

    @pytest.mark.asyncio
    async def test_update_dog_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_dog(uuid.uuid4(), DogProfileUpdate(name="x"))

    @pytest.mark.asyncio
    async def test_update_dog_status(self, service, mock_repo):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0003", name="Rex", breed="Mix",
            gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        result = await service.update_dog_status(dog_id, DogStatus.SHELTER, actor_id=uuid.uuid4())
        assert result.status == DogStatus.SHELTER

    @pytest.mark.asyncio
    async def test_soft_delete_dog(self, service, mock_repo):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0004", name="Rocky", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        await service.soft_delete_dog(dog_id, actor_id=uuid.uuid4())
        assert dog.deleted_at is not None

    @pytest.mark.asyncio
    async def test_soft_delete_dog_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_dog(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_dogs_paginated(self, service, mock_repo):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-0005", name="Oscar",
            breed="Poodle", gender="male", status=DogStatus.SHELTER, is_adoptable=True,
        )
        mock_repo.list_paginated.return_value = ([dog], 1)
        page = PageParams(page=1, page_size=20)
        sort = SortParams(sort_by="name", sort_order="asc")
        result = await service.list_dogs_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert len(result.data) == 1
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_bulk_update_status(self, service, mock_repo):
        ids = [uuid.uuid4(), uuid.uuid4()]
        mock_repo.bulk_update_status.return_value = 2
        count = await service.bulk_update_status(ids, DogStatus.ADOPTED, actor_id=uuid.uuid4())
        assert count == 2

    @pytest.mark.asyncio
    async def test_bulk_soft_delete(self, service, mock_repo):
        ids = [uuid.uuid4(), uuid.uuid4()]
        dog1 = _make_dog(id=ids[0], registration_number="DOG-001", name="A", breed="X", gender="male", status=DogStatus.SHELTER, is_adoptable=False)
        dog2 = _make_dog(id=ids[1], registration_number="DOG-002", name="B", breed="Y", gender="female", status=DogStatus.SHELTER, is_adoptable=False)
        mock_repo.get_by_id.side_effect = [dog1, dog2]
        count = await service.bulk_soft_delete(ids, actor_id=uuid.uuid4())
        assert count == 2
