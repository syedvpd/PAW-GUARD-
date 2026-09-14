import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams
from pawguard.modules.adoption.models import (
    AdoptionApplication,
    AdoptionFollowUp,
    AdoptionStatus,
    FollowUpStatus,
)
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import AdoptionApplicationResponse
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.reports.service import ReportService
from pawguard.modules.shelter.repository import ShelterRepository


def _make_app(**kw) -> AdoptionApplication:
    now = datetime.now(UTC)
    vals = dict(
        id=uuid.uuid4(),
        dog_id=uuid.uuid4(),
        adopter_id=uuid.uuid4(),
        residential_status="owned",
        status=AdoptionStatus.SUBMITTED,
        has_landlord_approval=False,
        has_yard_fence=False,
        household_members_count=1,
        is_foster_to_adopt=False,
        created_at=now,
        updated_at=now,
        vetting_officer_notes=None,
        completed_at=None,
    )
    vals.update(kw)
    app = AdoptionApplication(**vals)
    app.follow_ups = kw.get("follow_ups", [])
    return app


class TestAdoptionFollowUpReportingFields:
    """Test schema and model level derived fields for follow-ups and reporting."""

    def test_adoption_application_response_without_followups(self):
        app = _make_app(status=AdoptionStatus.SUBMITTED)
        resp = AdoptionApplicationResponse.model_validate(app)

        assert resp.submitted_at == app.created_at
        assert resp.created_at == app.created_at
        assert resp.completed_at is None
        assert resp.rejection_reason is None
        assert resp.reason is None
        assert resp.follow_ups == []
        assert resp.follow_up_records == []

    def test_adoption_application_response_with_followups(self):
        app_id = uuid.uuid4()
        now = datetime.now(UTC)
        fu1 = AdoptionFollowUp(
            id=uuid.uuid4(),
            adoption_application_id=app_id,
            due_day=30,
            due_at=now + timedelta(days=30),
            status=FollowUpStatus.SUBMITTED,
            submitted_at=now + timedelta(days=25),
            media_keys=["documents/photo1.jpg"],
            notes="Dog is healthy and happy",
            created_at=now,
            updated_at=now,
        )
        fu2 = AdoptionFollowUp(
            id=uuid.uuid4(),
            adoption_application_id=app_id,
            due_day=90,
            due_at=now + timedelta(days=90),
            status=FollowUpStatus.PENDING,
            submitted_at=None,
            media_keys=None,
            notes=None,
            created_at=now,
            updated_at=now,
        )
        app = _make_app(
            id=app_id,
            status=AdoptionStatus.COMPLETED,
            completed_at=now,
            follow_ups=[fu1, fu2],
        )

        resp = AdoptionApplicationResponse.model_validate(app)

        assert resp.status == AdoptionStatus.COMPLETED
        assert resp.completed_at == now
        assert len(resp.follow_ups) == 2
        assert len(resp.follow_up_records) == 2
        assert resp.follow_ups[0].due_day == 30
        assert resp.follow_ups[0].status == FollowUpStatus.SUBMITTED
        assert resp.follow_ups[0].media_keys == ["documents/photo1.jpg"]
        assert resp.follow_ups[1].due_day == 90
        assert resp.follow_ups[1].status == FollowUpStatus.PENDING

    def test_adoption_rejection_reason_extraction(self):
        app = _make_app(
            status=AdoptionStatus.REJECTED,
            vetting_officer_notes="Applicant background checked.\nRejection Reason: Yard fence height insufficient.",
        )
        resp = AdoptionApplicationResponse.model_validate(app)

        assert resp.status == AdoptionStatus.REJECTED
        assert resp.rejection_reason == "Yard fence height insufficient."
        assert resp.reason == "Yard fence height insufficient."

    def test_adoption_dict_validation_preserves_derived_fields(self):
        now = datetime.now(UTC)
        raw_dict = {
            "id": uuid.uuid4(),
            "dog_id": uuid.uuid4(),
            "adopter_id": uuid.uuid4(),
            "status": "rejected",
            "residential_status": "rented",
            "has_landlord_approval": True,
            "has_yard_fence": False,
            "household_members_count": 2,
            "existing_pets_medical_details": None,
            "pet_care_experience": None,
            "vetting_officer_notes": "Landlord revoked consent",
            "interview_scheduled_at": None,
            "interview_notes": None,
            "interview_completed_at": None,
            "home_inspection_scheduled_at": None,
            "home_inspection_notes": None,
            "home_inspection_type": None,
            "adoption_agreement_url": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
            "follow_ups": [],
        }
        resp = AdoptionApplicationResponse.model_validate(raw_dict)
        assert resp.submitted_at == now
        assert resp.rejection_reason == "Landlord revoked consent"
        assert resp.reason == "Landlord revoked consent"
        assert resp.follow_up_records == []


@pytest.mark.asyncio
class TestAdoptionServiceFollowUpWorkflow:
    """Test service-level behavior for follow-ups and application listing."""

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=AdoptionRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        return AsyncMock(spec=DogRepository)

    @pytest.fixture
    def mock_shelter_repo(self):
        return AsyncMock(spec=ShelterRepository)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_shelter_repo):
        return AdoptionService(
            repository=mock_repo,
            dog_repo=mock_dog_repo,
            shelter_repo=mock_shelter_repo,
            redis_client=None,
            audit_service=None,
            storage_service=None,
            notification_service=None,
        )

    async def test_list_applications_paginated_returns_follow_ups(self, service, mock_repo):
        now = datetime.now(UTC)
        app_id = uuid.uuid4()
        fu = AdoptionFollowUp(
            id=uuid.uuid4(),
            adoption_application_id=app_id,
            due_day=30,
            due_at=now + timedelta(days=30),
            status=FollowUpStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        app = _make_app(id=app_id, status=AdoptionStatus.COMPLETED, follow_ups=[fu])
        mock_repo.list_paginated.return_value = ([app], 1)

        result = await service.list_applications_paginated(
            page=PageParams(page=1, page_size=10),
            sort=SortParams(),
        )

        assert len(result.data) == 1
        app_data = result.data[0]
        assert len(app_data.follow_ups) == 1
        assert len(app_data.follow_up_records) == 1
        assert app_data.follow_ups[0].due_day == 30
        assert app_data.follow_ups[0].status == FollowUpStatus.PENDING

    async def test_completion_auto_initializes_follow_ups(self, service, mock_repo, mock_dog_repo):
        app_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        app = _make_app(
            id=app_id,
            dog_id=dog_id,
            status=AdoptionStatus.APPROVED,
        )
        mock_repo.get_by_id.return_value = app
        mock_repo.get_approved_application_for_dog.return_value = None
        mock_repo.get_follow_ups_for_application.return_value = []
        dog = DogProfile(id=dog_id, name="Buddy", is_adoptable=True, status=DogStatus.SHELTER)
        mock_dog_repo.get_by_id_for_update.return_value = dog
        mock_dog_repo.get_by_id.return_value = dog

        await service.update_application_status(
            app_id=app_id,
            status=AdoptionStatus.COMPLETED,
        )

        # Verify 3 follow-up milestones (30, 90, 180 days) were created
        assert mock_repo.create_follow_up.call_count == 3
        created_days = [call.args[0].due_day for call in mock_repo.create_follow_up.call_args_list]
        assert sorted(created_days) == [30, 90, 180]


@pytest.mark.asyncio
class TestReportServiceAdoptionCompliance:
    """Test ReportService adoption report compliance and follow-up calculation."""

    async def test_adoption_report_calculates_follow_up_compliance(self):
        now = datetime.now(UTC)
        app1_id = uuid.uuid4()
        fu1 = AdoptionFollowUp(
            id=uuid.uuid4(),
            adoption_application_id=app1_id,
            due_day=30,
            due_at=now - timedelta(days=10),
            status=FollowUpStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )
        fu2 = AdoptionFollowUp(
            id=uuid.uuid4(),
            adoption_application_id=app1_id,
            due_day=90,
            due_at=now - timedelta(days=2),
            status=FollowUpStatus.OVERDUE,
            created_at=now,
            updated_at=now,
        )
        fu3 = AdoptionFollowUp(
            id=uuid.uuid4(),
            adoption_application_id=app1_id,
            due_day=180,
            due_at=now + timedelta(days=80),
            status=FollowUpStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        app1 = _make_app(
            id=app1_id,
            status=AdoptionStatus.COMPLETED,
            completed_at=now - timedelta(days=100),
            follow_ups=[fu1, fu2, fu3],
        )

        app2 = _make_app(
            status=AdoptionStatus.REJECTED,
            vetting_officer_notes="Rejection Reason: Space constraints",
            follow_ups=[],
        )

        mock_session = AsyncMock()
        report_svc = ReportService(session=mock_session)

        # Mock fetch calls
        report_svc._fetch_adoption_apps = AsyncMock(return_value=[app1, app2])
        report_svc._fetch_adoption_scores = AsyncMock(return_value=[])

        from pawguard.modules.reports.schemas import ReportType

        report_data = await report_svc._collect_data(
            report_type=ReportType.ADOPTION,
            period_start=now.date() - timedelta(days=180),
            period_end=now.date(),
            filters=None,
        )

        assert report_data["title"] == "Adoption Report"
        # Find Vetting & Pipeline section
        vetting_section = next(
            s for s in report_data["sections"] if s["title"] == "Vetting & Pipeline"
        )
        rows_dict = dict(vetting_section["rows"])
        assert rows_dict["Total Applications"] == "2"
        assert rows_dict["Completed"] == "1"
        # 1 submitted out of (1 submitted + 1 overdue) = 50.0%
        assert rows_dict["Follow-Up Compliance"] == "50.0%"

        # Follow-up milestones section
        milestones_section = next(
            s for s in report_data["sections"] if s["title"] == "Post-Adoption Follow-Up Milestones"
        )
        milestones_dict = dict(milestones_section["rows"])
        assert milestones_dict["Submitted"] == "1"
        assert milestones_dict["Pending"] == "1"
        assert milestones_dict["Overdue"] == "1"
