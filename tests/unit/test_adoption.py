"""Unit tests for AdoptionService with mocked repositories."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import (
    AdoptionApplication,
    AdoptionFollowUp,
    AdoptionStatus,
    FollowUpStatus,
)
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import (
    AdoptionApplicationCreate,
    AdoptionApplicationUpdate,
    AdoptionScoreCreate,
)
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService


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
        mock_repo.get_application_by_adopter_and_dog.return_value = None
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
    async def test_apply_for_adoption_duplicate_application(
        self, service, mock_dog_repo, mock_repo
    ):
        """A second application by the same adopter for the same dog is
        rejected with 409 Conflict (PRR 3.7 one-active-application rule)."""
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="B", breed="Mix",
            gender="female", status=DogStatus.SHELTER, is_adoptable=True,
        )
        mock_repo.get_approved_application_for_dog.return_value = None
        mock_repo.get_application_by_adopter_and_dog.return_value = AdoptionApplication(
            id=uuid.uuid4(), dog_id=dog_id, adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
        )
        payload = AdoptionApplicationCreate(dog_id=dog_id, residential_status="owned")
        with pytest.raises(ConflictError, match="already submitted"):
            await service.apply_for_adoption(uuid.uuid4(), payload)
        mock_repo.get_application_by_adopter_and_dog.assert_awaited_once()
        mock_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_application(self, service, mock_repo):
        app_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SCREENING, residential_status="owned",
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
            status=AdoptionStatus.HOME_CHECK, residential_status="owned",
        )
        mock_repo.get_by_id.side_effect = [app, app]
        mock_repo.get_approved_application_for_dog.return_value = None
        dog = DogProfile(
            id=dog_id, registration_number="DOG-001", name="B", breed="Mix",
            gender="female", status=DogStatus.SHELTER, is_adoptable=True,
        )
        mock_dog_repo.get_by_id.return_value = dog
        mock_dog_repo.get_by_id_for_update.return_value = dog
        result = await service.update_application_status(app_id, AdoptionStatus.APPROVED, actor_id=uuid.uuid4())
        assert result.status == AdoptionStatus.APPROVED
        mock_dog_repo.get_by_id_for_update.assert_awaited_once_with(dog_id)

    @pytest.mark.asyncio
    async def test_update_application_status_invalid_transition(self, service, mock_repo):
        app_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
        )
        mock_repo.get_by_id.return_value = app
        with pytest.raises(ValidationFailedError, match="Cannot transition"):
            await service.update_application_status(app_id, AdoptionStatus.APPROVED)

    @pytest.mark.asyncio
    async def test_home_check_locks_dog_against_other_applications(
        self, service, mock_repo, mock_dog_repo
    ):
        app_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=dog_id, adopter_id=uuid.uuid4(),
            status=AdoptionStatus.INTERVIEW, residential_status="owned",
        )
        mock_repo.get_by_id.side_effect = [app, app]
        mock_repo.get_approved_application_for_dog.return_value = None
        dog = DogProfile(
            id=dog_id, registration_number="DOG-001", name="B", breed="Mix",
            gender="female", status=DogStatus.SHELTER, is_adoptable=True,
        )
        mock_dog_repo.get_by_id_for_update.return_value = dog
        result = await service.update_application_status(app_id, AdoptionStatus.HOME_CHECK)
        assert result.status == AdoptionStatus.HOME_CHECK
        assert dog.is_adoptable is False

    @pytest.mark.asyncio
    async def test_home_check_conflicts_with_other_locked_application(
        self, service, mock_repo, mock_dog_repo
    ):
        app_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=dog_id, adopter_id=uuid.uuid4(),
            status=AdoptionStatus.INTERVIEW, residential_status="owned",
        )
        other_app = AdoptionApplication(
            id=uuid.uuid4(), dog_id=dog_id, adopter_id=uuid.uuid4(),
            status=AdoptionStatus.HOME_CHECK, residential_status="owned",
        )
        mock_repo.get_by_id.return_value = app
        mock_repo.get_approved_application_for_dog.return_value = other_app
        with pytest.raises(ConflictError, match="already reached home inspection"):
            await service.update_application_status(app_id, AdoptionStatus.HOME_CHECK)

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

    @pytest.mark.asyncio
    async def test_approve_generates_agreement(self, mock_repo, mock_dog_repo, mock_audit):
        app_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        adopter_id = uuid.uuid4()
        adopter = User(id=adopter_id, full_name="Jane Doe", email="jane@example.com")
        dog = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Buddy",
            breed="Lab", gender="male", status=DogStatus.SHELTER,
            is_adoptable=True,
        )
        app = AdoptionApplication(
            id=app_id, dog_id=dog_id, adopter_id=adopter_id,
            dog=dog, adopter=adopter,
            status=AdoptionStatus.HOME_CHECK, residential_status="owned",
        )
        mock_repo.get_by_id.side_effect = [app, app]
        mock_repo.get_approved_application_for_dog.return_value = None
        mock_repo._session = AsyncMock()
        mock_dog_repo.get_by_id.return_value = dog
        mock_dog_repo.get_by_id_for_update.return_value = dog

        mock_storage = AsyncMock(spec=StorageService)
        mock_storage.build_object_key.return_value = "documents/agreement_test.pdf"

        svc = AdoptionService(
            mock_repo, mock_dog_repo, audit_service=mock_audit,
            storage_service=mock_storage,
        )
        result = await svc.update_application_status(
            app_id, AdoptionStatus.APPROVED, actor_id=uuid.uuid4(),
        )
        assert result.adoption_agreement_url == "documents/agreement_test.pdf"
        mock_storage.put_object.assert_called_once()
        call_kwargs = mock_storage.put_object.call_args.kwargs
        assert call_kwargs["content_type"] == "application/pdf"
        assert len(call_kwargs["content"]) > 0

    @pytest.mark.asyncio
    async def test_six_phase_transition_matrix(self, service, mock_repo, mock_dog_repo):
        """Every valid transition in the 6-phase pipeline succeeds and
        every invalid transition raises ValidationFailedError."""
        valid_transitions = {
            AdoptionStatus.SUBMITTED: [AdoptionStatus.SCREENING, AdoptionStatus.REJECTED],
            AdoptionStatus.SCREENING: [AdoptionStatus.INTERVIEW, AdoptionStatus.REJECTED],
            AdoptionStatus.INTERVIEW: [AdoptionStatus.HOME_CHECK, AdoptionStatus.REJECTED],
            AdoptionStatus.HOME_CHECK: [AdoptionStatus.APPROVED, AdoptionStatus.REJECTED],
            AdoptionStatus.APPROVED: [AdoptionStatus.COMPLETED, AdoptionStatus.REJECTED],
            AdoptionStatus.COMPLETED: [],
            AdoptionStatus.REJECTED: [],
        }
        for start_status, allowed in valid_transitions.items():
            for end_status in allowed:
                app_id = uuid.uuid4()
                dog_id = uuid.uuid4()
                app = AdoptionApplication(
                    id=app_id, dog_id=dog_id, adopter_id=uuid.uuid4(),
                    status=start_status, residential_status="owned",
                )
                mock_repo.get_by_id.return_value = app
                mock_repo.get_approved_application_for_dog.return_value = None
                mock_dog_repo.get_by_id.return_value = DogProfile(
                    id=dog_id, registration_number="DOG-001", name="B",
                    breed="Mix", gender="female", status=DogStatus.SHELTER,
                    is_adoptable=True,
                )
                mock_dog_repo.get_by_id_for_update.return_value = mock_dog_repo.get_by_id.return_value
                result = await service.update_application_status(
                    app_id, end_status, actor_id=uuid.uuid4(),
                )
                assert result.status == end_status

            for end_status in AdoptionStatus:
                if end_status in allowed or end_status == start_status:
                    continue
                app_id = uuid.uuid4()
                app = AdoptionApplication(
                    id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
                    status=start_status, residential_status="owned",
                )
                mock_repo.get_by_id.return_value = app
                with pytest.raises(ValidationFailedError, match="Cannot transition"):
                    await service.update_application_status(
                        app_id, end_status, actor_id=uuid.uuid4(),
                    )

    @pytest.mark.asyncio
    async def test_update_application_fee_in_agreement(self, mock_repo, mock_dog_repo, mock_audit):
        """Agreement PDF must reflect the actual fee_amount, not a hardcoded 0.0."""
        from unittest.mock import patch

        app_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        adopter_id = uuid.uuid4()
        adopter = User(id=adopter_id, full_name="Jane Doe", email="jane@example.com")
        dog = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Buddy",
            breed="Lab", gender="male", status=DogStatus.SHELTER,
            is_adoptable=True,
        )
        app = AdoptionApplication(
            id=app_id, dog_id=dog_id, adopter_id=adopter_id,
            dog=dog, adopter=adopter,
            status=AdoptionStatus.HOME_CHECK, residential_status="owned",
            fee_amount=Decimal("250.00"),
        )
        mock_repo.get_by_id.side_effect = [app, app]
        mock_repo.get_approved_application_for_dog.return_value = None
        mock_repo._session = AsyncMock()
        mock_dog_repo.get_by_id.return_value = dog
        mock_dog_repo.get_by_id_for_update.return_value = dog

        mock_storage = AsyncMock(spec=StorageService)
        mock_storage.build_object_key.return_value = "documents/agreement_test.pdf"

        with patch(
            "pawguard.modules.adoption.service.generate_adoption_agreement"
        ) as mock_gen:
            mock_gen.return_value = b"%PDF-1.4 fake pdf"
            svc = AdoptionService(
                mock_repo, mock_dog_repo, audit_service=mock_audit,
                storage_service=mock_storage,
            )
            await svc.update_application_status(
                app_id, AdoptionStatus.APPROVED, actor_id=uuid.uuid4(),
            )
            mock_gen.assert_called_once()
            call_kwargs = mock_gen.call_args.kwargs
            assert call_kwargs["fee_amount"] == 250.0

    @pytest.mark.asyncio
    async def test_record_followup_proof(self, service, mock_repo):
        follow_up_id = uuid.uuid4()
        follow_up = AdoptionFollowUp(
            id=follow_up_id, adoption_application_id=uuid.uuid4(),
            due_day=30, due_at=datetime.now(UTC),
            status=FollowUpStatus.PENDING,
        )
        mock_repo.get_follow_up_by_id.return_value = follow_up

        result = await service.record_followup_proof(
            follow_up_id,
            media_keys=["documents/proof.jpg"],
            notes="Dog is doing well.",
            actor_id=uuid.uuid4(),
        )

        assert result.status == FollowUpStatus.SUBMITTED
        assert result.submitted_at is not None
        assert result.media_keys == ["documents/proof.jpg"]
        assert result.notes == "Dog is doing well."

    @pytest.mark.asyncio
    async def test_record_followup_proof_already_submitted(self, service, mock_repo):
        follow_up_id = uuid.uuid4()
        follow_up = AdoptionFollowUp(
            id=follow_up_id, adoption_application_id=uuid.uuid4(),
            due_day=30, due_at=datetime.now(UTC),
            status=FollowUpStatus.SUBMITTED,
        )
        mock_repo.get_follow_up_by_id.return_value = follow_up

        with pytest.raises(ConflictError, match="already been submitted"):
            await service.record_followup_proof(
                follow_up_id,
                media_keys=["documents/proof.jpg"],
            )

    @pytest.mark.asyncio
    async def test_find_due_follow_ups_creates_milestones(self, service, mock_repo):
        """find_due_follow_ups creates missing milestone rows for completed apps."""
        app_id = uuid.uuid4()
        completed_at = datetime.now(UTC) - timedelta(days=45)
        app = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.COMPLETED,
            completed_at=completed_at,
            residential_status="owned",
        )
        mock_repo.get_completed_applications.return_value = [app]
        mock_repo.get_follow_up_for_milestone.side_effect = [None, None, None]
        mock_repo.get_due_follow_ups.return_value = []

        await service.find_due_follow_ups(now=datetime.now(UTC))

        assert mock_repo.create_follow_up.call_count == 3

    @pytest.mark.asyncio
    async def test_update_adoption_fee(self, service, mock_repo):
        app_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
            fee_amount=Decimal("0.00"),
        )
        mock_repo.get_by_id.side_effect = [app, app]

        result = await service.update_adoption_fee(
            app_id, Decimal("150.00"), actor_id=uuid.uuid4(),
        )
        assert result.fee_amount == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_update_adoption_fee_after_completed_raises(self, service, mock_repo):
        app_id = uuid.uuid4()
        app = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.COMPLETED, residential_status="owned",
            fee_amount=Decimal("0.00"),
        )
        mock_repo.get_by_id.return_value = app

        with pytest.raises(ConflictError, match="Cannot update the fee"):
            await service.update_adoption_fee(app_id, Decimal("150.00"))


class TestAdoptionScores:
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
    async def test_add_score_success(self, service, mock_repo, mock_audit):
        app_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
        )

        def _capture_score(score):
            score.id = uuid.uuid4()
            return score

        mock_repo.create_score.side_effect = _capture_score

        payload = AdoptionScoreCreate(
            home_environment_score=8,
            pet_care_knowledge_score=7,
            financial_readiness_score=6,
            lifestyle_compatibility_score=9,
            recommendation="approved",
        )
        result = await service.add_score(app_id, payload, actor_id=actor_id)
        assert result.overall_score == 7.5
        assert result.recommendation == "approved"
        assert result.scored_by_id == actor_id
        assert result.application_id == app_id
        mock_audit.record.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_scores_empty(self, service, mock_repo):
        app_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = AdoptionApplication(
            id=app_id, dog_id=uuid.uuid4(), adopter_id=uuid.uuid4(),
            status=AdoptionStatus.SUBMITTED, residential_status="owned",
        )
        mock_repo.get_scores_for_application.return_value = []
        result = await service.get_scores(app_id)
        assert result == []
