"""Unit tests for FosterService with mocked repositories."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.foster.models import (
    FosterPlacement,
    FosterProfile,
    FosterStatus,
    SupplyItemType,
)
from pawguard.modules.foster.repository import FosterRepository
from pawguard.modules.foster.schemas import (
    FosterPlacementCreate,
    FosterProfileCreate,
    FosterProfileUpdate,
    FosterProgressLogCreate,
    FosterReturnRequest,
    FosterSupplyDispatchCreate,
    FosterVetCheckRequest,
)
from pawguard.modules.foster.service import FosterService
from pawguard.services.audit_service import AuditService


def _make_foster(**kw):
    now = datetime.now(UTC)
    vals = dict(
        status=FosterStatus.APPLIED,
        max_capacity=1,
        active_count=0,
        is_available=True,
        background_check_passed=True,
        home_inspection_passed=True,
        created_at=now,
        updated_at=now,
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
        repo = AsyncMock(spec=DogRepository)
        repo.get_by_id_for_update.side_effect = lambda *a, **kw: repo.get_by_id.return_value
        return repo

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
            id=profile_id,
            user_id=user_id,
            status=FosterStatus.APPLIED,
            max_capacity=2,
            is_available=True,
        )
        payload = FosterProfileCreate(max_capacity=2)
        result = await service.apply_to_foster(user_id, payload, actor_id=uuid.uuid4())
        assert result.status == FosterStatus.APPLIED

    @pytest.mark.asyncio
    async def test_apply_to_foster_already_exists(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_profile_by_user_id.return_value = FosterProfile(
            id=uuid.uuid4(),
            user_id=user_id,
            status=FosterStatus.APPLIED,
        )
        with pytest.raises(ConflictError, match="already applied"):
            await service.apply_to_foster(user_id, FosterProfileCreate())

    @pytest.mark.asyncio
    async def test_update_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        profile = FosterProfile(
            id=profile_id,
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
            max_capacity=2,
            is_available=True,
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
    async def test_approving_foster_grants_role(self, service, mock_repo):
        profile_id = uuid.uuid4()
        user_id = uuid.uuid4()
        profile = FosterProfile(
            id=profile_id,
            user_id=user_id,
            status=FosterStatus.APPLIED,
            max_capacity=2,
            is_available=True,
            background_check_passed=True,
            references_checked=True,
            home_inspection_passed=True,
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]

        foster_role = type("Role", (), {"id": uuid.uuid4(), "name": "foster_family"})()
        with (
            patch.object(service._roles, "get_by_name", AsyncMock(return_value=foster_role)),
            patch.object(service._user_roles, "grant_role", AsyncMock()) as mock_grant,
        ):
            await service.update_profile(
                profile_id, FosterProfileUpdate(status=FosterStatus.APPROVED)
            )
            mock_grant.assert_awaited_once_with(user_id, foster_role.id)

    @pytest.mark.asyncio
    async def test_approving_foster_with_pending_checks_succeeds(self, service, mock_repo):
        profile_id = uuid.uuid4()
        user_id = uuid.uuid4()
        profile = FosterProfile(
            id=profile_id,
            user_id=user_id,
            status=FosterStatus.APPLIED,
            max_capacity=2,
            is_available=True,
            background_check_passed=None,
            references_checked=None,
            home_inspection_passed=None,
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]

        foster_role = type("Role", (), {"id": uuid.uuid4(), "name": "foster_family"})()
        with (
            patch.object(service._roles, "get_by_name", AsyncMock(return_value=foster_role)),
            patch.object(service._user_roles, "grant_role", AsyncMock()) as mock_grant,
        ):
            res = await service.update_profile(
                profile_id, FosterProfileUpdate(status=FosterStatus.APPROVED)
            )
            assert res.status == FosterStatus.APPROVED
            assert res.background_check_passed is True
            assert res.references_checked is True
            assert res.home_inspection_passed is True
            assert res.vetted_at is not None
            assert res.inspected_at is not None
            mock_grant.assert_awaited_once_with(user_id, foster_role.id)

    @pytest.mark.asyncio
    async def test_approving_foster_with_failed_check_raises_422(self, service, mock_repo):
        from pawguard.core.exceptions import ValidationFailedError

        profile_id = uuid.uuid4()
        user_id = uuid.uuid4()
        profile = FosterProfile(
            id=profile_id,
            user_id=user_id,
            status=FosterStatus.APPLIED,
            max_capacity=2,
            is_available=True,
            background_check_passed=False,
            references_checked=True,
            home_inspection_passed=True,
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]

        with pytest.raises(ValidationFailedError, match="failed background check"):
            await service.update_profile(
                profile_id, FosterProfileUpdate(status=FosterStatus.APPROVED)
            )

    @pytest.mark.asyncio
    async def test_get_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = FosterProfile(
            id=profile_id,
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
            max_capacity=2,
            is_available=True,
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
            id=foster_id,
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
            max_capacity=2,
            active_count=0,
            is_available=True,
            background_check_passed=True,
            home_inspection_passed=True,
        )
        mock_repo.get_profile_by_id_for_update.return_value = foster
        mock_dog_repo.get_by_id_for_update.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="Rex",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        mock_repo.get_active_placement_for_dog.return_value = None
        with patch(
            "pawguard.modules.foster.service.MedicalRepository.get_latest_approved_clearance",
            AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        ):
            uuid.uuid4()
            mock_repo.create_placement.return_value = None
            # place_dog re-fetches the placement before returning (so the response
            # serializer sees non-expired columns) - configure that mock too.
            mock_repo.get_placement_by_id.return_value = FosterPlacement(
                id=uuid.uuid4(),
                foster_id=foster_id,
                dog_id=dog_id,
                is_active=True,
                placed_at=datetime.now(),
            )
            payload = FosterPlacementCreate(dog_id=dog_id)
            result = await service.place_dog(foster_id, payload, actor_id=uuid.uuid4())
        assert result.dog_id == dog_id
        assert foster.active_count == 1

    @pytest.mark.asyncio
    async def test_place_dog_not_approved(self, service, mock_repo):
        foster = FosterProfile(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status=FosterStatus.APPLIED,
            max_capacity=1,
            is_available=True,
        )
        mock_repo.get_profile_by_id_for_update.return_value = foster
        with pytest.raises(ConflictError, match="must be approved"):
            await service.place_dog(uuid.uuid4(), FosterPlacementCreate(dog_id=uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_return_dog(self, service, mock_repo, mock_dog_repo):
        placement_id = uuid.uuid4()
        foster_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=foster_id,
            dog_id=dog_id,
            is_active=True,
            placed_at=datetime.now(),
        )
        mock_repo.get_placement_by_id.return_value = placement
        foster = FosterProfile(
            id=foster_id,
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
            max_capacity=2,
            active_count=1,
            is_available=False,
        )
        mock_repo.get_profile_by_id.return_value = foster
        dog = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="Rex",
            breed="Mix",
            gender="male",
            status=DogStatus.FOSTERED,
            is_adoptable=False,
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
            id=uuid.uuid4(),
            foster_id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            is_active=False,
            placed_at=datetime.now(),
        )
        mock_repo.get_placement_by_id.return_value = placement
        with pytest.raises(ConflictError, match="already inactive"):
            await service.return_dog(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_profiles_paginated(self, service, mock_repo):
        profile = _make_foster(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
            max_capacity=2,
        )
        mock_repo.paginate_profiles.return_value = ([profile], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_profiles_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1


class TestFosterProgressLog:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=FosterRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        repo = AsyncMock(spec=DogRepository)
        repo.get_by_id_for_update.side_effect = lambda *a, **kw: repo.get_by_id.return_value
        return repo

    @pytest.fixture
    def mock_adoption_repo(self):
        return AsyncMock(spec=AdoptionRepository)

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_adoption_repo, mock_audit):
        return FosterService(mock_repo, mock_dog_repo, mock_adoption_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_log_progress_success(self, service, mock_repo, mock_audit):
        placement_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            is_active=True,
            placed_at=datetime.now(),
        )
        mock_repo.get_placement_by_id.return_value = placement
        mock_repo.create_progress_log.return_value = None
        payload = FosterProgressLogCreate(weight_kg=12.5, mood_rating=4)
        result = await service.log_daily_progress(
            placement_id,
            payload,
            actor_id=uuid.uuid4(),
        )
        assert result.weight_kg == 12.5
        assert result.mood_rating == 4

    @pytest.mark.asyncio
    async def test_log_progress_placement_not_active(self, service, mock_repo):
        placement_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            is_active=False,
            placed_at=datetime.now(),
        )
        mock_repo.get_placement_by_id.return_value = placement
        with pytest.raises(ConflictError, match="not active"):
            await service.log_daily_progress(
                placement_id,
                FosterProgressLogCreate(),
                actor_id=uuid.uuid4(),
            )


class TestFosterToAdopt:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=FosterRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        repo = AsyncMock(spec=DogRepository)
        repo.get_by_id_for_update.side_effect = lambda *a, **kw: repo.get_by_id.return_value
        return repo

    @pytest.fixture
    def mock_adoption_repo(self):
        return AsyncMock(spec=AdoptionRepository)

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_adoption_repo, mock_audit):
        return FosterService(mock_repo, mock_dog_repo, mock_adoption_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_convert_to_adoption(
        self,
        service,
        mock_repo,
        mock_dog_repo,
        mock_adoption_repo,
    ):
        placement_id = uuid.uuid4()
        foster_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        user_id = uuid.uuid4()
        dog = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="Rex",
            breed="Mix",
            gender="male",
            status=DogStatus.FOSTERED,
            is_adoptable=True,
        )
        placement = FosterPlacement(
            id=placement_id,
            foster_id=foster_id,
            dog_id=dog_id,
            is_active=True,
            placed_at=datetime.now(),
        )
        foster = FosterProfile(
            id=foster_id,
            user_id=user_id,
            status=FosterStatus.APPROVED,
            max_capacity=2,
            active_count=1,
            is_available=False,
        )
        mock_repo.get_placement_by_id.return_value = placement
        mock_repo.get_profile_by_id.return_value = foster
        mock_dog_repo.get_by_id.return_value = dog
        mock_adoption_repo.get_approved_application_for_dog.return_value = None
        app_id = uuid.uuid4()
        mock_adoption_repo.create.return_value = None
        mock_adoption_repo.get_by_id.return_value = AdoptionApplication(
            id=app_id,
            dog_id=dog_id,
            adopter_id=user_id,
            residential_status="foster",
            status=AdoptionStatus.APPROVED,
        )
        with (
            patch(
                "pawguard.modules.foster.service.MedicalRepository.get_latest_approved_clearance",
                AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            ),
            patch.object(service, "_generate_adoption_lease", AsyncMock()),
        ):
            result = await service.convert_to_adoption(
                placement_id,
                actor_id=uuid.uuid4(),
            )
        assert result.id == app_id
        assert result.status == AdoptionStatus.APPROVED
        assert placement.is_active is False
        assert dog.status == DogStatus.ADOPTED
        assert dog.is_adoptable is False

    @pytest.mark.asyncio
    async def test_convert_to_adopt_already_adopted(
        self,
        service,
        mock_repo,
        mock_dog_repo,
    ):
        placement_id = uuid.uuid4()
        foster_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=foster_id,
            dog_id=dog_id,
            is_active=True,
            placed_at=datetime.now(),
        )
        mock_repo.get_placement_by_id.return_value = placement
        mock_repo.get_profile_by_id.return_value = FosterProfile(
            id=foster_id,
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
            max_capacity=2,
            active_count=1,
            is_available=False,
        )
        dog = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="Rex",
            breed="Mix",
            gender="male",
            status=DogStatus.ADOPTED,
            is_adoptable=False,
        )
        mock_dog_repo.get_by_id.return_value = dog
        with pytest.raises(ConflictError, match="already been adopted"):
            await service.convert_to_adoption(placement_id)


class TestFosterSupplyDispatch:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=FosterRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        repo = AsyncMock(spec=DogRepository)
        repo.get_by_id_for_update.side_effect = lambda *a, **kw: repo.get_by_id.return_value
        return repo

    @pytest.fixture
    def mock_adoption_repo(self):
        return AsyncMock(spec=AdoptionRepository)

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_adoption_repo, mock_audit):
        return FosterService(mock_repo, mock_dog_repo, mock_adoption_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_log_supply_dispatch_success(self, service, mock_repo, mock_audit):
        placement_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            is_active=True,
            placed_at=datetime.now(),
        )
        mock_repo.get_placement_by_id.return_value = placement
        mock_repo.create_supply_dispatch.return_value = None
        payload = FosterSupplyDispatchCreate(item_type=SupplyItemType.FOOD, quantity=2)
        result = await service.log_supply_dispatch(
            placement_id,
            payload,
            actor_id=uuid.uuid4(),
        )
        assert result.item_type == SupplyItemType.FOOD
        assert result.quantity == 2

    @pytest.mark.asyncio
    async def test_log_supply_dispatch_placement_not_found(self, service, mock_repo):
        mock_repo.get_placement_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.log_supply_dispatch(
                uuid.uuid4(),
                FosterSupplyDispatchCreate(item_type=SupplyItemType.FOOD),
            )


class TestFosterVetCheck:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=FosterRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        repo = AsyncMock(spec=DogRepository)
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_audit):
        return FosterService(mock_repo, mock_dog_repo, audit_service=mock_audit)

    @pytest.mark.asyncio
    async def test_request_vet_check_success(self, service, mock_repo, mock_dog_repo, mock_audit):
        placement_id = uuid.uuid4()
        foster_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=foster_id,
            dog_id=dog_id,
            is_active=True,
            placed_at=datetime.now(UTC),
        )
        mock_repo.get_placement_by_id.return_value = placement
        mock_repo.get_profile_by_id.return_value = FosterProfile(
            id=foster_id,
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
        )
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-VET-01",
            name="Charlie",
            breed="Labrador",
            gender="male",
        )
        mock_repo.create_progress_log.return_value = None

        payload = FosterVetCheckRequest(
            reason="Limping on front left paw",
            urgency="urgent",
            notes="Observed during morning walk.",
        )
        result = await service.request_vet_check(
            placement_id,
            payload,
            actor_id=uuid.uuid4(),
        )
        assert result.placement_id == placement_id
        assert result.dog_id == dog_id
        assert result.urgency == "urgent"
        assert result.status == "requested"
        mock_repo.create_progress_log.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_vet_check_inactive_placement_fails(self, service, mock_repo):
        placement_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            is_active=False,
            placed_at=datetime.now(UTC),
        )
        mock_repo.get_placement_by_id.return_value = placement
        payload = FosterVetCheckRequest(reason="Checkup")
        with pytest.raises(ConflictError, match="inactive"):
            await service.request_vet_check(placement_id, payload)


class TestFosterDailyProgressReporting:
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
        return FosterService(mock_repo, mock_dog_repo, audit_service=mock_audit)

    @pytest.mark.asyncio
    async def test_daily_progress_all_four_capabilities(self, service, mock_repo):
        placement_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            is_active=True,
            placed_at=datetime.now(UTC),
        )
        mock_repo.get_placement_by_id.return_value = placement
        mock_repo.create_progress_log.return_value = None

        # 1. Weight logs, 2. Behavioral logs, 3. Medication verification check-in, 4. Media uploads
        payload = FosterProgressLogCreate(
            weight_kg=18.5,
            behavior_notes="Calm, interacted nicely with children.",
            feeding_notes="Finished full meal.",
            medication_notes="Administered antibiotic tablet with food at 8 AM.",
            exercise_minutes=45,
            photo_urls=["https://storage.pawguard.io/fosters/rex_day3.jpg"],
            mood_rating=5,
            notes="Doing exceptionally well.",
        )
        result = await service.log_daily_progress(
            placement_id,
            payload,
            actor_id=uuid.uuid4(),
        )
        assert result.weight_kg == 18.5
        assert result.behavior_notes == "Calm, interacted nicely with children."
        assert result.medication_notes == "Administered antibiotic tablet with food at 8 AM."
        assert result.photo_urls == ["https://storage.pawguard.io/fosters/rex_day3.jpg"]
        assert result.mood_rating == 5
        assert result.exercise_minutes == 45
        mock_repo.create_progress_log.assert_awaited_once()


class TestFosterReturnToShelter:
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
        return FosterService(mock_repo, mock_dog_repo, audit_service=mock_audit)

    @pytest.mark.asyncio
    async def test_return_dog_success_and_state_updates(
        self, service, mock_repo, mock_dog_repo, mock_audit
    ):
        placement_id = uuid.uuid4()
        foster_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=foster_id,
            dog_id=dog_id,
            is_active=True,
            placed_at=datetime.now(UTC),
        )
        foster = FosterProfile(
            id=foster_id,
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
            max_capacity=1,
            active_count=1,
            is_available=False,
        )
        dog = DogProfile(
            id=dog_id,
            registration_number="DOG-RET-01",
            name="Bella",
            breed="Beagle",
            gender="female",
            status=DogStatus.FOSTERED,
        )
        mock_repo.get_placement_by_id.side_effect = [placement, placement]
        mock_repo.get_profile_by_id.return_value = foster
        mock_dog_repo.get_by_id.return_value = dog

        res = await service.return_dog(
            placement_id,
            notes="Placement term finished successfully.",
            actor_id=uuid.uuid4(),
        )
        assert res.is_active is False
        assert foster.active_count == 0
        assert foster.is_available is True
        assert dog.status == DogStatus.SHELTER

    @pytest.mark.asyncio
    async def test_return_dog_with_schema_notes(self, service, mock_repo, mock_dog_repo):
        placement_id = uuid.uuid4()
        foster_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        placement = FosterPlacement(
            id=placement_id,
            foster_id=foster_id,
            dog_id=dog_id,
            is_active=True,
            placed_at=datetime.now(UTC),
        )
        foster = FosterProfile(
            id=foster_id,
            user_id=uuid.uuid4(),
            status=FosterStatus.APPROVED,
            max_capacity=1,
            active_count=1,
            is_available=False,
        )
        dog = DogProfile(
            id=dog_id,
            registration_number="DOG-RET-02",
            name="Max",
            breed="Husky",
            gender="male",
            status=DogStatus.FOSTERED,
        )
        mock_repo.get_placement_by_id.side_effect = [placement, placement]
        mock_repo.get_profile_by_id.return_value = foster
        mock_dog_repo.get_by_id.return_value = dog

        req = FosterReturnRequest(notes="Completed medical recovery.", reason="Shelter request")
        res = await service.return_dog(
            placement_id,
            notes=req.notes,
        )
        assert res.is_active is False
