"""Unit tests for Adoption Availability synchronization and Lost & Found duplicate prevention."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.lost_found.models import (
    FoundReport,
    LostReport,
    ReportStatus,
    Species,
)
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import FoundReportCreate, LostReportCreate
from pawguard.modules.lost_found.service import LostFoundService

# ---------------------------------------------------------------------------
# ADOPTION AVAILABILITY / ZEUS EXCLUSION TESTS
# ---------------------------------------------------------------------------


class TestAdoptionAvailability:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        return session

    @pytest.fixture
    def dog_repo(self, mock_session):
        return DogRepository(mock_session)

    @pytest.mark.asyncio
    async def test_adoptable_dog_query_builds_completed_subquery(self, dog_repo, mock_session):
        """Verify list_paginated filters out both DogStatus.ADOPTED and dogs with COMPLETED adoptions."""
        # Setup mock return
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result

        # Execute list_paginated with is_adoptable=True
        await dog_repo.list_paginated(
            page=PageParams(page=1, page_size=20),
            sort=SortParams(sort_by="name", sort_order="asc"),
            is_adoptable=True,
        )

        # Inspect generated statement
        call_args = mock_session.execute.call_args_list[0]
        stmt = call_args[0][0]
        stmt_str = str(stmt)

        # Ensure the query enforces status != 'adopted' and checks completed adoption subquery
        assert "dog_profiles.is_adoptable = true" in stmt_str.lower()
        assert "dog_profiles.status !=" in stmt_str.lower()
        assert "adoption_applications" in stmt_str.lower()
        assert "deleted_at is null" in stmt_str.lower()

    @pytest.mark.asyncio
    async def test_adoption_completion_workflow_syncs_status_and_invalidates_cache(self):
        """Verify completion workflow sets dog to ADOPTED, is_adoptable=False, and clears cache."""
        from pawguard.modules.adoption.repository import AdoptionRepository
        from pawguard.modules.adoption.service import AdoptionService

        mock_repo = AsyncMock(spec=AdoptionRepository)
        mock_repo._session = AsyncMock()
        mock_dog_repo = AsyncMock(spec=DogRepository)

        dog_id = uuid.uuid4()
        app_id = uuid.uuid4()

        mock_dog = DogProfile(
            id=dog_id,
            name="Zeus",
            status=DogStatus.SHELTER,
            is_adoptable=True,
            breed="German Shepherd",
        )
        mock_dog_repo.get_by_id_for_update.return_value = mock_dog
        mock_dog_repo.get_by_id.return_value = mock_dog

        mock_app = AdoptionApplication(
            id=app_id,
            dog_id=dog_id,
            adopter_id=uuid.uuid4(),
            status=AdoptionStatus.APPROVED,
        )
        mock_repo.get_by_id.return_value = mock_app
        mock_repo.get_approved_application_for_dog.return_value = mock_app

        mock_redis = AsyncMock()
        mock_redis.scan_iter = AsyncMock(return_value=[])

        service = AdoptionService(
            repository=mock_repo,
            dog_repo=mock_dog_repo,
            redis_client=mock_redis,
        )

        with patch(
            "pawguard.services.cache_service.CacheService.delete_prefix", new_callable=AsyncMock
        ) as mock_delete:
            res = await service.update_application_status(
                app_id=app_id,
                status=AdoptionStatus.COMPLETED,
            )

            assert res.status == AdoptionStatus.COMPLETED
            assert mock_dog.status == DogStatus.ADOPTED
            assert mock_dog.is_adoptable is False
            assert mock_delete.called


# ---------------------------------------------------------------------------
# LOST & FOUND DUPLICATE PREVENTION TESTS
# ---------------------------------------------------------------------------


class TestLostFoundDuplicatePrevention:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=LostFoundRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return LostFoundService(repository=mock_repo)

    @pytest.mark.asyncio
    async def test_lost_report_first_submission_creates_record(self, service, mock_repo):
        """Case A: First submission creates a new active record."""
        user_id = uuid.uuid4()
        payload = LostReportCreate(
            species=Species.DOG,
            pet_name="Max",
            breed="Labrador",
            color="Golden",
            location_address="Park Avenue 12",
            lost_at=datetime.now(UTC),
        )

        # No duplicate exists
        mock_repo.find_active_lost_duplicate.return_value = None
        mock_repo.get_lost_report_by_id.side_effect = lambda rep_id: LostReport(
            id=rep_id,
            user_id=user_id,
            species=payload.species,
            pet_name=payload.pet_name,
            breed=payload.breed,
            color=payload.color,
            location_address=payload.location_address,
            lost_at=payload.lost_at,
            status=ReportStatus.ACTIVE,
        )

        created = await service.report_lost_pet(user_id, payload)

        assert mock_repo.create_lost_report.called
        assert created.pet_name == "Max"
        assert created.status == ReportStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_lost_report_repeated_submission_returns_existing(self, service, mock_repo):
        """Case B: Repeated submission returns existing active report without creating a new record."""
        user_id = uuid.uuid4()
        existing_report_id = uuid.uuid4()
        payload = LostReportCreate(
            species=Species.DOG,
            pet_name="Max",
            breed="Labrador",
            color="Golden",
            location_address="Park Avenue 12",
            lost_at=datetime.now(UTC),
        )

        existing_report = LostReport(
            id=existing_report_id,
            user_id=user_id,
            species=payload.species,
            pet_name=payload.pet_name,
            breed=payload.breed,
            color=payload.color,
            location_address=payload.location_address,
            lost_at=payload.lost_at,
            status=ReportStatus.ACTIVE,
        )
        mock_repo.find_active_lost_duplicate.return_value = existing_report

        result = await service.report_lost_pet(user_id, payload)

        # Must return existing report
        assert result.id == existing_report_id
        # Must NOT call create_lost_report
        assert not mock_repo.create_lost_report.called

    @pytest.mark.asyncio
    async def test_lost_report_companion_pet_id_duplicate_prevention(self, service, mock_repo):
        """Case: Owned companion dog duplicate detection."""
        user_id = uuid.uuid4()
        companion_id = uuid.uuid4()
        payload = LostReportCreate(
            companion_pet_id=companion_id,
            species=Species.DOG,
            pet_name="Rocky",
            breed="Husky",
            color="Grey",
            location_address="Street 5",
            lost_at=datetime.now(UTC),
        )

        existing = LostReport(
            id=uuid.uuid4(),
            user_id=user_id,
            companion_pet_id=companion_id,
            species=Species.DOG,
            pet_name="Rocky",
            breed="Husky",
            color="Grey",
            location_address="Street 5",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        mock_repo.find_active_lost_duplicate.return_value = existing

        result = await service.report_lost_pet(user_id, payload)
        assert result.id == existing.id
        assert not mock_repo.create_lost_report.called

    @pytest.mark.asyncio
    async def test_found_report_repeated_submission_returns_existing(self, service, mock_repo):
        """Case E: Repeated submission of same found animal incident returns existing report."""
        user_id = uuid.uuid4()
        existing_id = uuid.uuid4()
        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="German Shepherd Mix",
            color_observed="Black/Tan",
            location_address="Main Market Road",
            found_at=datetime.now(UTC),
        )

        existing_found = FoundReport(
            id=existing_id,
            user_id=user_id,
            species=payload.species,
            breed_observed=payload.breed_observed.lower(),
            color_observed=payload.color_observed.lower(),
            location_address=payload.location_address,
            found_at=payload.found_at,
            status=ReportStatus.ACTIVE,
        )
        mock_repo.find_active_found_duplicate.return_value = existing_found

        result = await service.report_found_pet(user_id, payload)

        assert result.id == existing_id
        assert not mock_repo.create_found_report.called

    @pytest.mark.asyncio
    async def test_found_report_different_incident_creates_new(self, service, mock_repo):
        """Case F: Different found pet incident is allowed."""
        user_id = uuid.uuid4()
        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Pug",
            color_observed="Fawn",
            location_address="Different Sector 4",
            found_at=datetime.now(UTC),
        )

        mock_repo.find_active_found_duplicate.return_value = None
        mock_repo.get_found_report_by_id.side_effect = lambda rep_id: FoundReport(
            id=rep_id,
            user_id=user_id,
            species=payload.species,
            breed_observed=payload.breed_observed.lower(),
            color_observed=payload.color_observed.lower(),
            location_address=payload.location_address,
            found_at=payload.found_at,
            status=ReportStatus.ACTIVE,
        )

        created = await service.report_found_pet(user_id, payload)

        assert mock_repo.create_found_report.called
        assert created.breed_observed == "pug"
