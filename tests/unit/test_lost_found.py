"""Unit tests for LostFoundService with mocked repository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.lost_found.models import (
    FoundReport,
    LostReport,
    MatchStatus,
    ReportMatch,
    ReportStatus,
)
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import (
    FoundReportCreate,
    LostReportCreate,
    OwnershipClaimReview,
    OwnershipClaimSubmit,
)
from pawguard.modules.lost_found.service import LostFoundService
from pawguard.services.audit_service import AuditService


class TestLostFoundService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=LostFoundRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return LostFoundService(mock_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_report_lost_pet(self, service, mock_repo, mock_audit):
        user_id = uuid.uuid4()
        mock_repo.create_lost_report.return_value = None
        mock_repo.list_found_reports.return_value = []
        uuid.uuid4()
        mock_repo.create_lost_report.side_effect = None
        mock_repo._session.flush.return_value = None
        payload = LostReportCreate(
            pet_name="Max", breed="Labrador", color="Brown",
            location_address="123 Main St", lost_at=datetime.now(UTC),
        )
        result = await service.report_lost_pet(user_id, payload, actor_id=uuid.uuid4())
        assert result.pet_name == "Max"
        assert result.status == ReportStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_report_found_pet(self, service, mock_repo, mock_audit):
        user_id = uuid.uuid4()
        mock_repo.create_found_report.return_value = None
        mock_repo.list_lost_reports.return_value = []
        mock_repo._session.flush.return_value = None
        payload = FoundReportCreate(
            breed_observed="Labrador", color_observed="Brown",
            location_address="456 Oak St", found_at=datetime.now(UTC),
        )
        result = await service.report_found_pet(user_id, payload, actor_id=uuid.uuid4())
        assert result.breed_observed == "labrador"
        assert result.status == ReportStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_resolve_lost_report(self, service, mock_repo):
        report_id = uuid.uuid4()
        report = LostReport(
            id=report_id, user_id=uuid.uuid4(), pet_name="Max",
            breed="labrador", color="brown", location_address="Addr",
            lost_at=datetime.now(UTC), status=ReportStatus.ACTIVE,
        )
        mock_repo.get_lost_report_by_id.return_value = report
        result = await service.resolve_lost_report(report_id, actor_id=uuid.uuid4())
        assert result.status == ReportStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_resolve_lost_report_not_found(self, service, mock_repo):
        mock_repo.get_lost_report_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.resolve_lost_report(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_resolve_found_report(self, service, mock_repo):
        report_id = uuid.uuid4()
        report = FoundReport(
            id=report_id, user_id=uuid.uuid4(),
            breed_observed="labrador", color_observed="brown",
            location_address="Addr", found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        mock_repo.get_found_report_by_id.return_value = report
        result = await service.resolve_found_report(report_id, actor_id=uuid.uuid4())
        assert result.status == ReportStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_resolve_found_report_not_found(self, service, mock_repo):
        mock_repo.get_found_report_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.resolve_found_report(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_matches_for_lost(self, service, mock_repo):
        report_id = uuid.uuid4()
        match = ReportMatch(
            lost_report_id=report_id, found_report_id=uuid.uuid4(),
            confidence_score=85.0, status=MatchStatus.PENDING,
        )
        mock_repo.list_matches_for_lost_report.return_value = [match]
        results = await service.get_matches_for_lost(report_id)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_matches_for_found(self, service, mock_repo):
        report_id = uuid.uuid4()
        match = ReportMatch(
            lost_report_id=uuid.uuid4(), found_report_id=report_id,
            confidence_score=75.0, status=MatchStatus.PENDING,
        )
        mock_repo.list_matches_for_found_report.return_value = [match]
        results = await service.get_matches_for_found(report_id)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_lost_reports_paginated(self, service, mock_repo):
        report = LostReport(
            id=uuid.uuid4(), user_id=uuid.uuid4(), pet_name="Max",
            breed="labrador", color="brown", location_address="Addr",
            lost_at=datetime.now(UTC), status=ReportStatus.ACTIVE,
        )
        mock_repo.list_lost_reports_paginated.return_value = ([report], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_lost_reports_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_list_found_reports_paginated(self, service, mock_repo):
        report = FoundReport(
            id=uuid.uuid4(), user_id=uuid.uuid4(),
            breed_observed="labrador", color_observed="brown",
            location_address="Addr", found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        mock_repo.list_found_reports_paginated.return_value = ([report], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_found_reports_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_list_matches_paginated(self, service, mock_repo):
        match = ReportMatch(
            lost_report_id=uuid.uuid4(), found_report_id=uuid.uuid4(),
            confidence_score=90.0, status=MatchStatus.PENDING,
        )
        mock_repo.list_matches_paginated.return_value = ([match], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_matches_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_lost_report(self, service, mock_repo):
        report_id = uuid.uuid4()
        mock_repo.soft_delete_lost_report.return_value = True
        await service.soft_delete_lost_report(report_id, actor_id=uuid.uuid4())
        mock_repo.soft_delete_lost_report.assert_called_once_with(report_id)

    @pytest.mark.asyncio
    async def test_soft_delete_lost_report_not_found(self, service, mock_repo):
        mock_repo.soft_delete_lost_report.return_value = False
        with pytest.raises(NotFoundError):
            await service.soft_delete_lost_report(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_soft_delete_found_report(self, service, mock_repo):
        report_id = uuid.uuid4()
        mock_repo.soft_delete_found_report.return_value = True
        await service.soft_delete_found_report(report_id, actor_id=uuid.uuid4())
        mock_repo.soft_delete_found_report.assert_called_once_with(report_id)

    @pytest.mark.asyncio
    async def test_soft_delete_found_report_not_found(self, service, mock_repo):
        mock_repo.soft_delete_found_report.return_value = False
        with pytest.raises(NotFoundError):
            await service.soft_delete_found_report(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_match_status(self, service, mock_repo):
        match_id = uuid.uuid4()
        match = ReportMatch(
            id=match_id, lost_report_id=uuid.uuid4(), found_report_id=uuid.uuid4(),
            confidence_score=80.0, status=MatchStatus.PENDING,
        )
        mock_repo.get_match_by_id.return_value = match
        result = await service.update_match_status(match_id, MatchStatus.CONFIRMED)
        assert result.status == MatchStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_update_match_status_not_found(self, service, mock_repo):
        mock_repo.get_match_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_match_status(uuid.uuid4(), MatchStatus.CONFIRMED)

    @pytest.mark.asyncio
    async def test_evaluate_match_score_exact(self, service):
        lost = LostReport(
            id=uuid.uuid4(), user_id=uuid.uuid4(), pet_name="M", breed="labrador",
            color="brown", location_address="Addr", lost_at=datetime.now(UTC),
            latitude=40.0, longitude=-74.0, status=ReportStatus.ACTIVE,
        )
        found = FoundReport(
            id=uuid.uuid4(), user_id=uuid.uuid4(), breed_observed="labrador",
            color_observed="brown", location_address="Addr2",
            found_at=datetime.now(UTC), latitude=40.001, longitude=-74.001,
            status=ReportStatus.ACTIVE,
        )
        score = service._evaluate_match_score(lost, found)
        assert score >= 90.0


class TestOwnershipClaimWorkflow:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=LostFoundRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return LostFoundService(mock_repo, mock_audit)

    def _match(self, lost_owner_id, found_reporter_id, **kw):
        lost = LostReport(
            id=uuid.uuid4(), user_id=lost_owner_id, pet_name="Max",
            breed="labrador", color="brown", location_address="Addr",
            lost_at=datetime.now(UTC), status=ReportStatus.ACTIVE,
        )
        found = FoundReport(
            id=uuid.uuid4(), user_id=found_reporter_id,
            breed_observed="labrador", color_observed="brown",
            location_address="Addr2", found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        vals = dict(
            id=uuid.uuid4(), lost_report_id=lost.id, found_report_id=found.id,
            lost_report=lost, found_report=found, confidence_score=88.0,
            status=MatchStatus.PENDING,
        )
        vals.update(kw)
        return ReportMatch(**vals)

    @pytest.mark.asyncio
    async def test_submit_claim_success(self, service, mock_repo, mock_audit):
        owner_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4())
        mock_repo.get_match_by_id.return_value = match
        payload = OwnershipClaimSubmit(
            microchip_doc_url="https://example.com/chip.pdf",
            vet_bill_url="https://example.com/bill.pdf",
        )
        result = await service.submit_ownership_claim(
            match.id, owner_id, payload, actor_id=owner_id, ip_address="203.0.113.9",
        )
        assert result.claim_submitted_at is not None
        assert result.microchip_doc_url == "https://example.com/chip.pdf"
        mock_audit.record.assert_awaited_once()
        kwargs = mock_audit.record.call_args.kwargs
        assert kwargs["event_type"].value == "lost_found_claim_submitted"
        assert kwargs["metadata"]["proof_types"] == ["microchip_doc", "vet_bill"]

    @pytest.mark.asyncio
    async def test_submit_claim_requires_reporter(self, service, mock_repo):
        match = self._match(uuid.uuid4(), uuid.uuid4())
        mock_repo.get_match_by_id.return_value = match
        stranger_id = uuid.uuid4()
        with pytest.raises(ForbiddenError, match="reporter"):
            await service.submit_ownership_claim(
                match.id, stranger_id, OwnershipClaimSubmit(photo_proof_url="x"),
            )

    @pytest.mark.asyncio
    async def test_submit_claim_requires_proof_document(self, service, mock_repo):
        owner_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4())
        mock_repo.get_match_by_id.return_value = match
        with pytest.raises(ValidationFailedError, match="proof document"):
            await service.submit_ownership_claim(
                match.id, owner_id, OwnershipClaimSubmit(),
            )

    @pytest.mark.asyncio
    async def test_submit_claim_rejected_after_review(self, service, mock_repo):
        owner_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4(), status=MatchStatus.CONFIRMED)
        mock_repo.get_match_by_id.return_value = match
        with pytest.raises(ValidationFailedError, match="already been reviewed"):
            await service.submit_ownership_claim(
                match.id, owner_id, OwnershipClaimSubmit(photo_proof_url="x"),
            )

    @pytest.mark.asyncio
    async def test_review_claim_approve_confirms_and_resolves(
        self, service, mock_repo, mock_audit
    ):
        owner_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4(), claim_submitted_at=datetime.now(UTC))
        mock_repo.get_match_by_id.return_value = match
        mock_repo.get_lost_report_by_id.return_value = match.lost_report
        mock_repo.get_found_report_by_id.return_value = match.found_report
        result = await service.review_ownership_claim(
            match.id, OwnershipClaimReview(approve=True),
            actor_id=reviewer_id, ip_address="203.0.113.9",
        )
        assert result.status == MatchStatus.CONFIRMED
        assert result.claim_reviewed_by == reviewer_id
        assert result.claim_reviewed_at is not None
        assert match.lost_report.status == ReportStatus.RESOLVED
        assert match.found_report.status == ReportStatus.RESOLVED
        mock_audit.record.assert_called()
        reviewed = [c for c in mock_audit.record.call_args_list
                    if c.kwargs["event_type"].value == "lost_found_claim_reviewed"]
        assert reviewed, "claim_reviewed audit event must be recorded"

    @pytest.mark.asyncio
    async def test_review_claim_reject_marks_rejected(self, service, mock_repo):
        owner_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4(), claim_submitted_at=datetime.now(UTC))
        mock_repo.get_match_by_id.return_value = match
        result = await service.review_ownership_claim(
            match.id, OwnershipClaimReview(approve=False),
            actor_id=uuid.uuid4(),
        )
        assert result.status == MatchStatus.REJECTED

    @pytest.mark.asyncio
    async def test_review_claim_requires_submission(self, service, mock_repo):
        match = self._match(uuid.uuid4(), uuid.uuid4())
        mock_repo.get_match_by_id.return_value = match
        with pytest.raises(ValidationFailedError, match="(?i)no ownership claim"):
            await service.review_ownership_claim(
                match.id, OwnershipClaimReview(approve=True),
            )

    @pytest.mark.asyncio
    async def test_get_match(self, service, mock_repo):
        match_id = uuid.uuid4()
        mock_repo.get_match_by_id.return_value = self._match(
            uuid.uuid4(), uuid.uuid4(), id=match_id,
        )
        result = await service.get_match(match_id)
        assert result.id == match_id

    @pytest.mark.asyncio
    async def test_get_match_not_found(self, service, mock_repo):
        mock_repo.get_match_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_match(uuid.uuid4())
