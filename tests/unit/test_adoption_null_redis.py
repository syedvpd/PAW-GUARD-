"""Unit test verifying AdoptionService succeeds when initialized with _NullRedis."""

import uuid
from unittest.mock import AsyncMock

import pytest

from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import AdoptionApplicationCreate
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.redis.client import _NullRedis


@pytest.mark.asyncio
async def test_apply_for_adoption_with_null_redis() -> None:
    mock_repo = AsyncMock(spec=AdoptionRepository)
    mock_dog_repo = AsyncMock(spec=DogRepository)
    null_redis = _NullRedis()

    service = AdoptionService(
        repository=mock_repo,
        dog_repo=mock_dog_repo,
        redis_client=null_redis,
    )

    dog_id = uuid.uuid4()
    adopter_id = uuid.uuid4()

    mock_dog_repo.get_by_id.return_value = DogProfile(
        id=dog_id,
        registration_number="DOG-2026-0002",
        name="Bella",
        breed="Labrador Retriever",
        gender="female",
        status=DogStatus.SHELTER,
        is_adoptable=True,
    )
    mock_repo.get_approved_application_for_dog.return_value = None
    mock_repo.get_application_by_adopter_and_dog.return_value = None
    mock_repo.create.return_value = None

    app_id = uuid.uuid4()
    mock_repo.get_by_id.return_value = AdoptionApplication(
        id=app_id,
        dog_id=dog_id,
        adopter_id=adopter_id,
        status=AdoptionStatus.SUBMITTED,
        residential_status="owned",
        has_landlord_approval=True,
        has_yard_fence=True,
        household_members_count=2,
    )

    payload = AdoptionApplicationCreate(
        dog_id=dog_id,
        residential_status="owned",
        has_landlord_approval=True,
        has_yard_fence=True,
        household_members_count=2,
    )

    result = await service.apply_for_adoption(adopter_id, payload)
    assert result.id == app_id
    assert result.status == AdoptionStatus.SUBMITTED
