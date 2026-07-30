"""Unit tests for FosterService with mocked repositories."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.foster.models import FosterPlacement, FosterProfile, FosterStatus
from pawguard.modules.foster.repository import FosterRepository
from pawguard.modules.foster.schemas import (
    FosterPlacementCreate,
    FosterProfileCreate,
    FosterProfileUpdate,
)
from pawguard.modules.foster.service import FosterService
from pawguard.services.audit_service import AuditService


def _make_foster(**kw):
    now = datetime.now(UTC)
    vals = dict(
        status=FosterStatus.APPLIED, max_capacity=1, active_count=0,
        is_available=True, created_at=now, updated_at=now,
    )
    vals.update(kw)
    return FosterProfile(**vals)


class TestFosterService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=FosterRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        return AsyncMock(spec=DogRepository)

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_audit):
        return FosterService(mock_repo, mock_dog_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_apply_to_foster(self, service, mock_repo, mock_audit):
        user_id = uuid.uuid4()
        mock_repo.get_profile_by_user_id.return_value = None
        profile_id = uuid.uuid4()
        mock_repo.create_profile.return_value = None
        mock_repo.get_profile_by_id.return_value = FosterProfile(
            id=profile_id, user_id=user_id, status=FosterStatus.APPLIED,
            max_capacity=2, is_available=True,
        )
        payload = FosterProfileCreate(max_capacity=2)
        result = await service.apply_to_foster(user_id, payload, actor_id=uuid.uuid4())
        assert result.status == FosterStatus.APPLIED

    @pytest.mark.asyncio
    async def test_apply_to_foster_already_exists(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_profile_by_user_id.return_value = FosterProfile(
            id=uuid.uuid4(), user_id=user_id, status=FosterStatus.APPLIED,
        )
        with pytest.raises(ConflictError, match="already applied"):
            await service.apply_to_foster(user_id, FosterProfileCreate())

    @pytest.mark.asyncio
    async def test_update_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        profile = FosterProfile(
            id=profile_id, user_id=uuid.uuid4(), status=FosterStatus.APPROVED,
            max_capacity=2, is_available=True,
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]
        payload = FosterProfileUpdate(max_capacity=3)
        result = await service.update_profile(profile_id, payload, actor_id=uuid.uuid4())
        assert result.max_capacity == 3

    @pytest.mark.asyncio
    async def test_update_profile_not_found(self, service, mock_repo):
        mock_repo.get_profile_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_profile(uuid.uuid4(), FosterProfileUpdate())

    @pytest.mark.asyncio
    async def test_get_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = FosterProfile(
            id=profile_id, user_id=uuid.uuid4(), status=FosterStatus.APPROVED,
            max_capacity=2, is_available=True,
        )
        result = await service.get_profile(profile_id)
        assert result.id == profile_id

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, service, mock_repo):
        mock_repo.get_profile_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_profile(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_place_dog(self, service, mock_repo, mock_dog_repo):
        foster_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        foster = FosterProfile(
            id=foster_id, user_id=uuid.uuid4(), status=FosterStatus.APPROVED,
            max_capacity=2, active_count=0, is_available=True,
        )
        mock_repo.get_profile_by_id.return_value = foster
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_active_placement_for_dog.return_value = None
        uuid.uuid4()
        mock_repo.create_placement.return_value = None
        payload = FosterPlacementCreate(dog_id=dog_id)
        result = await service.place_dog(foster_id, payload, actor_id=uuid.uuid4())
        assert result.dog_id == dog_id
        assert foster.active_count == 1

    @pytest.mark.asyncio
    async def test_place_dog_not_approved(self, service, mock_repo):
        foster = FosterProfile(
            id=uuid.uuid4(), user_id=uuid.uuid4(), status=FosterStatus.APPLIED,
            max_capacity=1, is_available=True,
        )
        mock_repo.get_profile_by_id.return_value = foster
        with pytest.raises(ConflictError, match="must be approved"):
            await service.place_dog(uuid.uuid4(), FosterPlacementCreate(dog_id=uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_return_dog(self, service, mock_repo, mock_dog_repo):
        placement_id = uuid.uuid4()
        foster_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id, foster_id=foster_id, dog_id=dog_id,
            is_active=True, placed_at=datetime.now(),
        )
        mock_repo.get_placement_by_id.return_value = placement
        foster = FosterProfile(
            id=foster_id, user_id=uuid.uuid4(), status=FosterStatus.APPROVED,
            max_capacity=2, active_count=1, is_available=False,
        )
        mock_repo.get_profile_by_id.return_value = foster
        dog = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.FOSTERED, is_adoptable=False,
        )
        mock_dog_repo.get_by_id.return_value = dog
        result = await service.return_dog(placement_id, notes="Returned", actor_id=uuid.uuid4())
        assert result.is_active is False
        assert foster.is_available is True
        assert dog.status == DogStatus.SHELTER

    @pytest.mark.asyncio
    async def test_return_dog_not_found(self, service, mock_repo):
        mock_repo.get_placement_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.return_dog(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_return_dog_already_inactive(self, service, mock_repo):
        placement = FosterPlacement(
            id=uuid.uuid4(), foster_id=uuid.uuid4(), dog_id=uuid.uuid4(),
            is_active=False, placed_at=datetime.now(),
        )
        mock_repo.get_placement_by_id.return_value = placement
        with pytest.raises(ConflictError, match="already inactive"):
            await service.return_dog(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_profiles_paginated(self, service, mock_repo):
        profile = _make_foster(
            id=uuid.uuid4(), user_id=uuid.uuid4(), status=FosterStatus.APPROVED,
            max_capacity=2,
        )
        mock_repo.paginate_profiles.return_value = ([profile], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_profiles_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1
