"""Unit tests for AdoptionService with mocked repositories."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import (
    AdoptionApplicationCreate,
    AdoptionApplicationUpdate,
)
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.services.audit_service import AuditService


def _make_app(**kw):
    now = datetime.now(UTC)
    vals = dict(
        residential_status="owned", status=AdoptionStatus.SUBMITTED,
        has_landlord_approval=False, has_yard_fence=False,
        household_members_count=1, created_at=now, updated_at=now,
    )
    vals.update(kw)
    return AdoptionApplication(**vals)


class TestAdoptionService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=AdoptionRepository)
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
        return AdoptionService(mock_repo, mock_dog_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_apply_for_adoption_success(self, service, mock_repo, mock_dog_repo, mock_audit):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Buddy", breed="Lab",
            gender="male", status=DogStatus.SHELTER, is_adoptable=True,
        )
        mock_repo.get_approved_application_for_dog.return_value = None
        mock_repo.create.return_value = None
        app_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = AdoptionApplication(
            id=app_id, dog_id=dog_id, adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
            has_landlord_approval=True, has_yard_fence=True,
            household_members_count=2,
        )
        payload = AdoptionApplicationCreate(
            dog_id=dog_id, residential_status="owned",
            has_landlord_approval=True, has_yard_fence=True,
        )
        result = await service.apply_for_adoption(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.status == AdoptionStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_apply_for_adoption_dog_not_found(self, service, mock_dog_repo):
        mock_dog_repo.get_by_id.return_value = None
        payload = AdoptionApplicationCreate(dog_id=uuid.uuid4(), residential_status="owned")
        with pytest.raises(NotFoundError, match="Dog profile not found"):
            await service.apply_for_adoption(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_apply_for_adoption_not_adoptable(self, service, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="B", breed="Mix",
            gender="female", status=DogStatus.SHELTER, is_adoptable=False,
        )
        payload = AdoptionApplicationCreate(dog_id=dog_id, residential_status="owned")
        with pytest.raises(ConflictError, match="not currently cleared"):
            await service.apply_for_adoption(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_apply_for_adoption_already_approved(self, service, mock_dog_repo, mock_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="B", breed="Mix",
            gender="female", status=DogStatus.SHELTER, is_adoptable=True,
        )
        mock_repo.get_approved_application_for_dog.return_value = AdoptionApplication(
            id=uuid.uuid4(), dog_id=dog_id, adopter_id=uuid.uuid4(),
            status=AdoptionStatus.APPROVED, residential_status="owned",
        )
        payload = AdoptionApplicationCreate(dog_id=dog_id, residential_status="owned")
        with pytest.raises(ConflictError, match="already under an approved"):
            await service.apply_for_adoption(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_update_application(self, service, mock_repo):
        app_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.VETTING, residential_status="owned",
            has_landlord_approval=True, has_yard_fence=True,
        )
        mock_repo.get_by_id.return_value = app
        payload = AdoptionApplicationUpdate(vetting_officer_notes="Looks good")
        mock_repo.get_by_id.side_effect = [app, app]
        result = await service.update_application(app_id, payload, actor_id=uuid.uuid4())
        assert result.vetting_officer_notes == "Looks good"

    @pytest.mark.asyncio
    async def test_update_application_status(self, service, mock_repo, mock_dog_repo):
        app_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=dog_id, adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
        )
        mock_repo.get_by_id.side_effect = [app, app]
        mock_repo.get_approved_application_for_dog.return_value = None
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="B", breed="Mix",
            gender="female", status=DogStatus.SHELTER, is_adoptable=True,
        )
        result = await service.update_application_status(app_id, AdoptionStatus.APPROVED, actor_id=uuid.uuid4())
        assert result.status == AdoptionStatus.APPROVED

    @pytest.mark.asyncio
    async def test_get_application(self, service, mock_repo):
        app_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
        )
        result = await service.get_application(app_id)
        assert result.id == app_id

    @pytest.mark.asyncio
    async def test_get_application_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_application(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_applications_paginated(self, service, mock_repo):
        app = _make_app(
            id=uuid.uuid4(), dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
        )
        mock_repo.list_paginated.return_value = ([app], 1)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_applications_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_application(self, service, mock_repo):
        app_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
        )
        mock_repo.get_by_id.return_value = app
        await service.soft_delete_application(app_id, actor_id=uuid.uuid4())
        assert app.deleted_at is not None

    @pytest.mark.asyncio
    async def test_soft_delete_application_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_application(uuid.uuid4())
