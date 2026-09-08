"""Unit tests for LostFoundService with mocked repository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import User
from pawguard.modules.lost_found.models import (
    FoundReport,
    LostReport,
    MatchStatus,
    ReportMatch,
    ReportMedia,
    ReportStatus,
    Species,
)
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import (
    FoundReportCreate,
    FoundReportResponse,
    LostReportCreate,
    LostReportResponse,
    OwnershipClaimReview,
    OwnershipClaimSubmit,
)
from pawguard.modules.lost_found.service import LostFoundService
from pawguard.services.audit_service import AuditService


class TestLostFoundBroadcastQueue:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=LostFoundRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def mock_arq(self):
        arq = AsyncMock()
        arq.enqueue_job = AsyncMock(return_value=None)
        return arq

    @pytest.fixture
    def service(self, mock_repo, mock_audit, mock_arq):
        return LostFoundService(mock_repo, mock_audit, arq_pool=mock_arq)

    @pytest.mark.asyncio
    async def test_queue_broadcast_success(self, service, mock_repo, mock_audit, mock_arq):
        owner_id = uuid.uuid4()
        report = LostReport(
            id=uuid.uuid4(),
            user_id=owner_id,
            pet_name="Max",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        mock_repo.get_lost_report_by_id.return_value = report
        result = await service.queue_lost_alert_broadcast(report.id, owner_id)
        assert result["queued"] is True
        mock_arq.enqueue_job.assert_awaited_once()
        mock_audit.record.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_queue_broadcast_not_found(self, service, mock_repo):
        mock_repo.get_lost_report_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.queue_lost_alert_broadcast(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_queue_broadcast_forbidden_stranger(self, service, mock_repo):
        owner_id = uuid.uuid4()
        report = LostReport(
            id=uuid.uuid4(),
            user_id=owner_id,
            pet_name="Max",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        mock_repo.get_lost_report_by_id.return_value = report
        with pytest.raises(ForbiddenError):
            await service.queue_lost_alert_broadcast(report.id, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_queue_broadcast_admin_bypass(self, service, mock_repo, mock_arq):
        owner_id = uuid.uuid4()
        report = LostReport(
            id=uuid.uuid4(),
            user_id=owner_id,
            pet_name="Max",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        mock_repo.get_lost_report_by_id.return_value = report
        result = await service.queue_lost_alert_broadcast(report.id, uuid.uuid4(), is_admin=True)
        assert result["queued"] is True
        mock_arq.enqueue_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_queue_broadcast_only_active(self, service, mock_repo):
        owner_id = uuid.uuid4()
        report = LostReport(
            id=uuid.uuid4(),
            user_id=owner_id,
            pet_name="Max",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            status=ReportStatus.RESOLVED,
        )
        mock_repo.get_lost_report_by_id.return_value = report
        with pytest.raises(ValidationFailedError):
            await service.queue_lost_alert_broadcast(report.id, owner_id)


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
        report_id = uuid.uuid4()
        mock_repo.create_lost_report.return_value = None
        mock_repo.list_found_reports.return_value = []
        mock_repo._session.flush.return_value = None

        payload = LostReportCreate(
            species=Species.CAT,
            pet_name="Max",
            breed="Persian",
            color="White",
            location_address="123 Main St",
            lost_at=datetime.now(UTC),
        )

        loaded_report = LostReport(
            id=report_id,
            user_id=user_id,
            species=Species.CAT,
            pet_name="Max",
            breed="persian",
            color="white",
            location_address="123 Main St",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            media=[],
        )
        mock_repo.get_lost_report_by_id.return_value = loaded_report

        result = await service.report_lost_pet(user_id, payload, actor_id=uuid.uuid4())
        assert result.pet_name == "Max"
        assert result.species == Species.CAT
        assert result.status == ReportStatus.ACTIVE

        # Verify Pydantic response model validation / serialization succeeds
        response_data = LostReportResponse.model_validate(result)
        assert response_data.id == report_id
        assert response_data.species == Species.CAT
        assert response_data.pet_name == "Max"

    @pytest.mark.asyncio
    async def test_report_found_pet(self, service, mock_repo, mock_audit):
        user_id = uuid.uuid4()
        report_id = uuid.uuid4()
        mock_repo.create_found_report.return_value = None
        mock_repo.list_lost_reports.return_value = []
        mock_repo._session.flush.return_value = None

        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Labrador",
            color_observed="Brown",
            location_address="456 Oak St",
            found_at=datetime.now(UTC),
        )

        loaded_report = FoundReport(
            id=report_id,
            user_id=user_id,
            species=Species.DOG,
            breed_observed="labrador",
            color_observed="brown",
            location_address="456 Oak St",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            media=[],
        )
        mock_repo.get_found_report_by_id.return_value = loaded_report

        result = await service.report_found_pet(user_id, payload, actor_id=uuid.uuid4())
        assert result.breed_observed == "labrador"
        assert result.species == Species.DOG
        assert result.status == ReportStatus.ACTIVE

        # Verify Pydantic response model validation / serialization succeeds
        response_data = FoundReportResponse.model_validate(result)
        assert response_data.id == report_id
        assert response_data.species == Species.DOG
        assert response_data.breed_observed == "labrador"

    @pytest.mark.asyncio
    async def test_report_lost_pet_eager_loads_reporter_before_matching(
        self, service, mock_repo, mock_audit
    ):
        """Match notifications must never lazy-load the freshly flushed report's
        reporter relationship (async MissingGreenlet -> DATABASE_QUERY_FAILED).
        The report is eagerly reloaded (repo get_lost_report_by_id) BEFORE the
        matcher runs so _notify_match reads a populated `lost.user`."""
        user_id = uuid.uuid4()
        report_id = uuid.uuid4()
        order: list[str] = []

        async def reload_side_effect(*_args, **_kwargs):
            order.append("reload")
            return LostReport(
                id=report_id,
                user_id=user_id,
                species=Species.CAT,
                pet_name="Max",
                breed="persian",
                color="white",
                location_address="123 Main St",
                lost_at=datetime.now(UTC),
                status=ReportStatus.ACTIVE,
                created_at=datetime.now(UTC),
                media=[],
                user=None,
            )

        async def match_side_effect(*_args, **_kwargs):
            order.append("match")
            return []

        mock_repo.create_lost_report.return_value = None
        mock_repo.get_lost_report_by_id.side_effect = reload_side_effect
        mock_repo.list_found_reports.side_effect = match_side_effect
        mock_repo._session.flush.return_value = None

        payload = LostReportCreate(
            species=Species.CAT,
            pet_name="Max",
            breed="Persian",
            color="White",
            location_address="123 Main St",
            lost_at=datetime.now(UTC),
        )
        await service.report_lost_pet(user_id, payload)
        assert order == ["reload", "match"]

    @pytest.mark.asyncio
    async def test_report_found_pet_eager_loads_reporter_before_matching(
        self, service, mock_repo, mock_audit
    ):
        """Match notifications must never lazy-load the freshly flushed report's
        reporter relationship (async MissingGreenlet -> DATABASE_QUERY_FAILED).
        The report is eagerly reloaded (repo get_found_report_by_id) BEFORE the
        matcher runs so _notify_match reads a populated `found.user`."""
        user_id = uuid.uuid4()
        report_id = uuid.uuid4()
        order: list[str] = []

        async def reload_side_effect(*_args, **_kwargs):
            order.append("reload")
            return FoundReport(
                id=report_id,
                user_id=user_id,
                species=Species.DOG,
                breed_observed="labrador",
                color_observed="golden",
                location_address="456 Oak St",
                found_at=datetime.now(UTC),
                status=ReportStatus.ACTIVE,
                created_at=datetime.now(UTC),
                media=[],
                user=None,
            )

        async def match_side_effect(*_args, **_kwargs):
            order.append("match")
            return []

        mock_repo.create_found_report.return_value = None
        mock_repo.get_found_report_by_id.side_effect = reload_side_effect
        mock_repo.list_lost_reports.side_effect = match_side_effect
        mock_repo._session.flush.return_value = None

        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Labrador",
            color_observed="Golden",
            location_address="456 Oak St",
            found_at=datetime.now(UTC),
        )
        await service.report_found_pet(user_id, payload)
        assert order == ["reload", "match"]

    @pytest.mark.asyncio
    async def test_resolve_lost_report(self, service, mock_repo):
        report_id = uuid.uuid4()
        report = LostReport(
            id=report_id,
            user_id=uuid.uuid4(),
            pet_name="Max",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
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
            id=report_id,
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr",
            found_at=datetime.now(UTC),
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
            lost_report_id=report_id,
            found_report_id=uuid.uuid4(),
            confidence_score=85.0,
            status=MatchStatus.PENDING,
        )
        mock_repo.list_matches_for_lost_report.return_value = [match]
        results = await service.get_matches_for_lost(report_id)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_matches_for_found(self, service, mock_repo):
        report_id = uuid.uuid4()
        match = ReportMatch(
            lost_report_id=uuid.uuid4(),
            found_report_id=report_id,
            confidence_score=75.0,
            status=MatchStatus.PENDING,
        )
        mock_repo.list_matches_for_found_report.return_value = [match]
        results = await service.get_matches_for_found(report_id)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_lost_reports_paginated(self, service, mock_repo):
        report = LostReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            pet_name="Max",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
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
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr",
            found_at=datetime.now(UTC),
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
            lost_report_id=uuid.uuid4(),
            found_report_id=uuid.uuid4(),
            confidence_score=90.0,
            status=MatchStatus.PENDING,
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
            id=match_id,
            lost_report_id=uuid.uuid4(),
            found_report_id=uuid.uuid4(),
            confidence_score=80.0,
            status=MatchStatus.PENDING,
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
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            pet_name="M",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            latitude=40.0,
            longitude=-74.0,
            status=ReportStatus.ACTIVE,
        )
        found = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr2",
            found_at=datetime.now(UTC),
            latitude=40.001,
            longitude=-74.001,
            status=ReportStatus.ACTIVE,
        )
        score, dist_km, gap_days, reasons = service._evaluate_match_score(lost, found)
        assert score >= 80.0
        assert isinstance(gap_days, float)
        assert isinstance(reasons, list)

    @pytest.mark.asyncio
    async def test_evaluate_match_score_temporal_gap(self, service):
        lost = LostReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            pet_name="M",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime(2026, 7, 1, tzinfo=UTC),
            latitude=40.0,
            longitude=-74.0,
            status=ReportStatus.ACTIVE,
        )
        found_close = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr2",
            found_at=datetime(2026, 7, 2, tzinfo=UTC),
            latitude=40.001,
            longitude=-74.001,
            status=ReportStatus.ACTIVE,
        )
        found_far = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr2",
            found_at=datetime(2026, 9, 1, tzinfo=UTC),
            latitude=40.001,
            longitude=-74.001,
            status=ReportStatus.ACTIVE,
        )
        score_close, _, gap_close, _ = service._evaluate_match_score(lost, found_close)
        score_far, _, gap_far, _ = service._evaluate_match_score(lost, found_far)
        assert gap_close < gap_far
        assert score_close > score_far

    @pytest.mark.asyncio
    async def test_evaluate_match_score_collar_boost(self, service):
        lost = LostReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            pet_name="M",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            latitude=40.0,
            longitude=-74.0,
            status=ReportStatus.ACTIVE,
            collar_color="Red",
        )
        found_match = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr2",
            found_at=datetime.now(UTC),
            latitude=40.001,
            longitude=-74.001,
            status=ReportStatus.ACTIVE,
            collar_color="Red",
        )
        found_no_collar = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr2",
            found_at=datetime.now(UTC),
            latitude=40.001,
            longitude=-74.001,
            status=ReportStatus.ACTIVE,
            collar_color=None,
        )
        score_with, _, _, _ = service._evaluate_match_score(lost, found_match)
        score_without, _, _, _ = service._evaluate_match_score(lost, found_no_collar)
        assert score_with > score_without

    @pytest.mark.asyncio
    async def test_evaluate_match_score_markers_boost(self, service):
        lost = LostReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            pet_name="M",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            latitude=40.0,
            longitude=-74.0,
            status=ReportStatus.ACTIVE,
            marker_description="White patch on left ear, scar on right leg",
        )
        found_match = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr2",
            found_at=datetime.now(UTC),
            latitude=40.001,
            longitude=-74.001,
            status=ReportStatus.ACTIVE,
            marker_description="white patch on left ear, limping",
        )
        found_no_match = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr2",
            found_at=datetime.now(UTC),
            latitude=40.001,
            longitude=-74.001,
            status=ReportStatus.ACTIVE,
            marker_description="tattoo on tail",
        )
        score_with, _, _, _ = service._evaluate_match_score(lost, found_match)
        score_without, _, _, _ = service._evaluate_match_score(lost, found_no_match)
        assert score_with > score_without

    @pytest.mark.asyncio
    async def test_evaluate_match_score_within_bounds(self, service):
        lost = LostReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            pet_name="M",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            latitude=40.0,
            longitude=-74.0,
            status=ReportStatus.ACTIVE,
        )
        found = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="poodle",
            color_observed="white",
            location_address="Addr2",
            found_at=datetime.now(UTC),
            latitude=45.0,
            longitude=-80.0,
            status=ReportStatus.ACTIVE,
        )
        score, dist_km, gap_days, reasons = service._evaluate_match_score(lost, found)
        assert 0.0 <= score <= 100.0
        assert isinstance(gap_days, float)
        assert isinstance(reasons, list)

    @pytest.mark.asyncio
    async def test_evaluate_match_score_no_match_below_threshold(self, service):
        lost = LostReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            pet_name="M",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            latitude=40.0,
            longitude=-74.0,
            status=ReportStatus.ACTIVE,
        )
        found = FoundReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            breed_observed="poodle",
            color_observed="white",
            location_address="Addr2",
            found_at=datetime.now(UTC),
            latitude=45.0,
            longitude=-80.0,
            status=ReportStatus.ACTIVE,
        )
        score, _, _, _ = service._evaluate_match_score(lost, found)
        assert score < 50.0


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
            id=uuid.uuid4(),
            user_id=lost_owner_id,
            pet_name="Max",
            breed="labrador",
            color="brown",
            location_address="Addr",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        found = FoundReport(
            id=uuid.uuid4(),
            user_id=found_reporter_id,
            breed_observed="labrador",
            color_observed="brown",
            location_address="Addr2",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        vals = dict(
            id=uuid.uuid4(),
            lost_report_id=lost.id,
            found_report_id=found.id,
            lost_report=lost,
            found_report=found,
            confidence_score=88.0,
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
            match.id,
            owner_id,
            payload,
            actor_id=owner_id,
            ip_address="203.0.113.9",
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
                match.id,
                stranger_id,
                OwnershipClaimSubmit(photo_proof_url="x"),
            )

    @pytest.mark.asyncio
    async def test_submit_claim_requires_proof_document(self, service, mock_repo):
        owner_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4())
        mock_repo.get_match_by_id.return_value = match
        with pytest.raises(ValidationFailedError, match="proof document"):
            await service.submit_ownership_claim(
                match.id,
                owner_id,
                OwnershipClaimSubmit(),
            )

    @pytest.mark.asyncio
    async def test_submit_claim_rejected_after_review(self, service, mock_repo):
        owner_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4(), status=MatchStatus.CONFIRMED)
        mock_repo.get_match_by_id.return_value = match
        with pytest.raises(ValidationFailedError, match="already been reviewed"):
            await service.submit_ownership_claim(
                match.id,
                owner_id,
                OwnershipClaimSubmit(photo_proof_url="x"),
            )

    @pytest.mark.asyncio
    async def test_review_claim_approve_confirms_and_resolves(self, service, mock_repo, mock_audit):
        owner_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4(), claim_submitted_at=datetime.now(UTC))
        mock_repo.get_match_by_id.return_value = match
        mock_repo.get_lost_report_by_id.return_value = match.lost_report
        mock_repo.get_found_report_by_id.return_value = match.found_report
        result = await service.review_ownership_claim(
            match.id,
            OwnershipClaimReview(approve=True),
            actor_id=reviewer_id,
            ip_address="203.0.113.9",
        )
        assert result.status == MatchStatus.CONFIRMED
        assert result.claim_reviewed_by == reviewer_id
        assert result.claim_reviewed_at is not None
        assert match.lost_report.status == ReportStatus.RESOLVED
        assert match.found_report.status == ReportStatus.RESOLVED
        mock_audit.record.assert_called()
        reviewed = [
            c
            for c in mock_audit.record.call_args_list
            if c.kwargs["event_type"].value == "lost_found_claim_reviewed"
        ]
        assert reviewed, "claim_reviewed audit event must be recorded"

    @pytest.mark.asyncio
    async def test_review_claim_reject_marks_rejected(self, service, mock_repo):
        owner_id = uuid.uuid4()
        match = self._match(owner_id, uuid.uuid4(), claim_submitted_at=datetime.now(UTC))
        mock_repo.get_match_by_id.return_value = match
        result = await service.review_ownership_claim(
            match.id,
            OwnershipClaimReview(approve=False),
            actor_id=uuid.uuid4(),
        )
        assert result.status == MatchStatus.REJECTED

    @pytest.mark.asyncio
    async def test_review_claim_requires_submission(self, service, mock_repo):
        match = self._match(uuid.uuid4(), uuid.uuid4())
        mock_repo.get_match_by_id.return_value = match
        with pytest.raises(ValidationFailedError, match="(?i)no ownership claim"):
            await service.review_ownership_claim(
                match.id,
                OwnershipClaimReview(approve=True),
            )

    @pytest.mark.asyncio
    async def test_get_match(self, service, mock_repo):
        match_id = uuid.uuid4()
        mock_repo.get_match_by_id.return_value = self._match(
            uuid.uuid4(),
            uuid.uuid4(),
            id=match_id,
        )
        result = await service.get_match(match_id)
        assert result.id == match_id

    @pytest.mark.asyncio
    async def test_get_match_not_found(self, service, mock_repo):
        mock_repo.get_match_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_match(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_lost_report_response_serialization_with_user_and_media(self):
        user_id = uuid.uuid4()
        report_id = uuid.uuid4()
        media_id = uuid.uuid4()
        user = User(
            id=user_id,
            email="owner@example.com",
            full_name="John Doe",
            phone="+919876543210",
            is_verified=True,
            mfa_enabled=False,
            push_notifications_enabled=True,
            roles=[],
        )
        media_item = ReportMedia(
            id=media_id,
            lost_report_id=report_id,
            media_type="photo",
            object_key="lost-found/sample.jpg",
            is_primary=True,
            display_order=0,
        )
        report = LostReport(
            id=report_id,
            user_id=user_id,
            species=Species.DOG,
            pet_name="Buddy",
            breed="beagle",
            color="tricolor",
            location_address="123 Main St",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=user,
            media=[media_item],
        )

        res = LostReportResponse.model_validate(report)
        assert res.id == report_id
        assert res.user is not None
        assert res.user.email == "owner@example.com"
        assert res.user.full_name == "John Doe"
        assert len(res.media) == 1
        assert res.media[0].id == media_id
        assert res.media[0].media_type == "photo"

    @pytest.mark.asyncio
    async def test_found_report_response_serialization_with_user_and_media(self):
        user_id = uuid.uuid4()
        report_id = uuid.uuid4()
        media_id = uuid.uuid4()
        user = User(
            id=user_id,
            email="finder@example.com",
            full_name="Jane Finder",
            phone="+919876543211",
            is_verified=True,
            mfa_enabled=False,
            push_notifications_enabled=True,
            roles=[],
        )
        media_item = ReportMedia(
            id=media_id,
            found_report_id=report_id,
            media_type="photo",
            object_key="lost-found/sample2.jpg",
            is_primary=True,
            display_order=0,
        )
        report = FoundReport(
            id=report_id,
            user_id=user_id,
            species=Species.CAT,
            breed_observed="persian",
            color_observed="white",
            location_address="456 Park Ave",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=user,
            media=[media_item],
        )

        res = FoundReportResponse.model_validate(report)
        assert res.id == report_id
        assert res.user is not None
        assert res.user.email == "finder@example.com"
        assert res.species == Species.CAT
        assert len(res.media) == 1
        assert res.media[0].id == media_id


class TestFoundReportDuplicateAndLockEnforcement:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=LostFoundRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.mark.asyncio
    async def test_redis_lock_failure_stops_execution_lost_report(self, mock_repo, mock_audit):
        mock_redis = AsyncMock()
        # acquire_lock returns False (simulate concurrent holder)
        mock_redis.set = AsyncMock(return_value=False)
        service = LostFoundService(mock_repo, mock_audit, redis=mock_redis)

        user_id = uuid.uuid4()
        payload = LostReportCreate(
            species=Species.DOG,
            pet_name="Buddy",
            breed="Labrador",
            color="Golden",
            location_address="123 MG Road",
            lost_at=datetime.now(UTC),
        )
        with pytest.raises(ConflictError, match="currently being processed"):
            await service.report_lost_pet(user_id, payload)

        # Critical section was NOT entered
        mock_repo.find_active_lost_duplicate.assert_not_called()
        mock_repo.create_lost_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_lock_failure_stops_execution_found_report(self, mock_repo, mock_audit):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)
        service = LostFoundService(mock_repo, mock_audit, redis=mock_redis)

        user_id = uuid.uuid4()
        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Labrador",
            color_observed="Golden",
            location_address="123 MG Road",
            found_at=datetime.now(UTC),
        )
        with pytest.raises(ConflictError, match="currently being processed"):
            await service.report_found_pet(user_id, payload)

        # Critical section was NOT entered
        mock_repo.find_active_found_duplicate.assert_not_called()
        mock_repo.create_found_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_found_incident_repeated_duplicate_prevented(self, mock_repo, mock_audit):
        # Redis lock succeeds
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.eval = AsyncMock(return_value=1)
        service = LostFoundService(mock_repo, mock_audit, redis=mock_redis)

        user_id = uuid.uuid4()
        existing_report = FoundReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            breed_observed="labrador",
            color_observed="golden",
            location_address="123 MG Road",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.find_active_found_duplicate.return_value = existing_report

        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Labrador",
            color_observed="Golden",
            location_address="123 MG Road",
            found_at=datetime.now(UTC),
        )
        result = await service.report_found_pet(user_id, payload)
        assert result.id == existing_report.id
        mock_repo.create_found_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_breed_same_location_different_incident_allowed(self, mock_repo, mock_audit):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.eval = AsyncMock(return_value=1)
        service = LostFoundService(mock_repo, mock_audit, redis=mock_redis)

        user_id = uuid.uuid4()
        # Different incident (different color, e.g. Black Lab vs Golden Lab on same street)
        mock_repo.find_active_found_duplicate.return_value = None

        new_report = FoundReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            breed_observed="labrador",
            color_observed="black",
            location_address="123 MG Road",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.create_found_report.return_value = new_report
        mock_repo.get_found_report_by_id.return_value = new_report

        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Labrador",
            color_observed="Black",
            location_address="123 MG Road",
            found_at=datetime.now(UTC),
        )
        result = await service.report_found_pet(user_id, payload)
        assert result.id == new_report.id
        mock_repo.create_found_report.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolved_old_incident_allows_new_report(self, mock_repo, mock_audit):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.eval = AsyncMock(return_value=1)
        service = LostFoundService(mock_repo, mock_audit, redis=mock_redis)

        user_id = uuid.uuid4()
        # Repository find_active_found_duplicate filters by status=ReportStatus.ACTIVE,
        # so an old RESOLVED report is not returned as a duplicate.
        mock_repo.find_active_found_duplicate.return_value = None

        new_report = FoundReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            breed_observed="labrador",
            color_observed="golden",
            location_address="123 MG Road",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.create_found_report.return_value = new_report
        mock_repo.get_found_report_by_id.return_value = new_report

        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Labrador",
            color_observed="Golden",
            location_address="123 MG Road",
            found_at=datetime.now(UTC),
        )
        result = await service.report_found_pet(user_id, payload)
        assert result.id == new_report.id
        mock_repo.create_found_report.assert_awaited_once()


class TestLostFoundModelIntegrity:
    """Regression test ensuring ReportMedia, FoundReport, and LostReport models
    correctly configure mappers without NoReferencedTableError or InvalidRequestError.
    """

    def test_lost_found_mappers_and_foreign_keys_configured(self):
        from sqlalchemy.orm import configure_mappers

        import pawguard.db.models  # noqa: F401
        from pawguard.db.base import Base

        configure_mappers()

        # Verify tables are registered in Base.metadata
        table_names = set(Base.metadata.tables.keys())
        assert "found_reports" in table_names
        assert "lost_reports" in table_names
        assert "report_media" in table_names
        assert "rescue_requests" in table_names
        assert "companion_pets" in table_names
        assert "users" in table_names

        # Verify ReportMedia foreign keys resolve target columns cleanly
        media_table = Base.metadata.tables["report_media"]
        for fk in media_table.foreign_keys:
            assert fk.column is not None


class TestLostFoundDuplicateResponseContract:
    """Authoritative test suite for Lost & Found duplicate response contract (Tasks 1-6)."""

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=LostFoundRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        redis.eval = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def service(self, mock_repo, mock_audit, mock_redis):
        return LostFoundService(mock_repo, mock_audit, redis=mock_redis)

    # ── TEST A: First submission (Lost & Found) ─────────────────────────
    @pytest.mark.asyncio
    async def test_lost_report_first_submission_is_duplicate_false(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.find_active_lost_duplicate.return_value = None
        new_id = uuid.uuid4()
        new_report = LostReport(
            id=new_id,
            user_id=user_id,
            species=Species.DOG,
            pet_name="Bruno",
            breed="labrador",
            color="golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.create_lost_report.return_value = new_report
        mock_repo.get_lost_report_by_id.return_value = new_report

        payload = LostReportCreate(
            species=Species.DOG,
            pet_name="Bruno",
            breed="Labrador",
            color="Golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
        )
        result = await service.report_lost_pet(user_id, payload)
        assert result.id == new_id
        assert getattr(result, "is_duplicate", None) is False
        assert getattr(result, "_is_duplicate", None) is False

        response_data = LostReportResponse.model_validate(result)
        assert response_data.is_duplicate is False
        mock_repo.create_lost_report.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_found_report_first_submission_is_duplicate_false(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.find_active_found_duplicate.return_value = None
        new_id = uuid.uuid4()
        new_report = FoundReport(
            id=new_id,
            user_id=user_id,
            species=Species.DOG,
            breed_observed="beagle",
            color_observed="tricolor",
            location_address="Jubilee Hills Checkpost",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.create_found_report.return_value = new_report
        mock_repo.get_found_report_by_id.return_value = new_report

        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Beagle",
            color_observed="Tricolor",
            location_address="Jubilee Hills Checkpost",
            found_at=datetime.now(UTC),
        )
        result = await service.report_found_pet(user_id, payload)
        assert result.id == new_id
        assert getattr(result, "is_duplicate", None) is False
        assert getattr(result, "_is_duplicate", None) is False

        response_data = FoundReportResponse.model_validate(result)
        assert response_data.is_duplicate is False
        mock_repo.create_found_report.assert_awaited_once()

    # ── TEST B: Sequential duplicate (Lost & Found) ──────────────────────
    @pytest.mark.asyncio
    async def test_lost_report_sequential_duplicate_returns_existing_with_is_duplicate_true(
        self, service, mock_repo
    ):
        user_id = uuid.uuid4()
        existing_id = uuid.uuid4()
        existing_report = LostReport(
            id=existing_id,
            user_id=user_id,
            species=Species.DOG,
            pet_name="Bruno",
            breed="labrador",
            color="golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.find_active_lost_duplicate.return_value = existing_report

        payload = LostReportCreate(
            species=Species.DOG,
            pet_name="Bruno",
            breed="Labrador",
            color="Golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
        )
        result = await service.report_lost_pet(user_id, payload)
        assert result.id == existing_id
        assert getattr(result, "is_duplicate", None) is True
        assert getattr(result, "_is_duplicate", None) is True

        response_data = LostReportResponse.model_validate(result)
        assert response_data.is_duplicate is True
        mock_repo.create_lost_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_found_report_sequential_duplicate_returns_existing_with_is_duplicate_true(
        self, service, mock_repo
    ):
        user_id = uuid.uuid4()
        existing_id = uuid.uuid4()
        existing_report = FoundReport(
            id=existing_id,
            user_id=user_id,
            species=Species.DOG,
            breed_observed="beagle",
            color_observed="tricolor",
            location_address="Jubilee Hills Checkpost",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.find_active_found_duplicate.return_value = existing_report

        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Beagle",
            color_observed="Tricolor",
            location_address="Jubilee Hills Checkpost",
            found_at=datetime.now(UTC),
        )
        result = await service.report_found_pet(user_id, payload)
        assert result.id == existing_id
        assert getattr(result, "is_duplicate", None) is True
        assert getattr(result, "_is_duplicate", None) is True

        response_data = FoundReportResponse.model_validate(result)
        assert response_data.is_duplicate is True
        mock_repo.create_found_report.assert_not_called()

    # ── TEST C: Concurrent duplicate (Redis lock contention) ────────────
    @pytest.mark.asyncio
    async def test_lost_concurrent_duplicate_redis_lock_contention(self, mock_repo, mock_audit):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)
        service = LostFoundService(mock_repo, mock_audit, redis=mock_redis)

        user_id = uuid.uuid4()
        payload = LostReportCreate(
            species=Species.DOG,
            pet_name="Bruno",
            breed="Labrador",
            color="Golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
        )
        with pytest.raises(ConflictError, match="currently being processed"):
            await service.report_lost_pet(user_id, payload)

        mock_repo.find_active_lost_duplicate.assert_not_called()
        mock_repo.create_lost_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_found_concurrent_duplicate_redis_lock_contention(self, mock_repo, mock_audit):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)
        service = LostFoundService(mock_repo, mock_audit, redis=mock_redis)

        user_id = uuid.uuid4()
        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Beagle",
            color_observed="Tricolor",
            location_address="Jubilee Hills Checkpost",
            found_at=datetime.now(UTC),
        )
        with pytest.raises(ConflictError, match="currently being processed"):
            await service.report_found_pet(user_id, payload)

        mock_repo.find_active_found_duplicate.assert_not_called()
        mock_repo.create_found_report.assert_not_called()

    # ── TEST D: Resolved / expired behavior ─────────────────────────────
    @pytest.mark.asyncio
    async def test_lost_resolved_report_does_not_block_new_submission(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.find_active_lost_duplicate.return_value = None
        new_report = LostReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            pet_name="Bruno",
            breed="labrador",
            color="golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.create_lost_report.return_value = new_report
        mock_repo.get_lost_report_by_id.return_value = new_report

        payload = LostReportCreate(
            species=Species.DOG,
            pet_name="Bruno",
            breed="Labrador",
            color="Golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
        )
        result = await service.report_lost_pet(user_id, payload)
        assert getattr(result, "is_duplicate", False) is False
        mock_repo.create_lost_report.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_found_resolved_report_does_not_block_new_submission(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.find_active_found_duplicate.return_value = None
        new_report = FoundReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            breed_observed="beagle",
            color_observed="tricolor",
            location_address="Jubilee Hills Checkpost",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.create_found_report.return_value = new_report
        mock_repo.get_found_report_by_id.return_value = new_report

        payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Beagle",
            color_observed="Tricolor",
            location_address="Jubilee Hills Checkpost",
            found_at=datetime.now(UTC),
        )
        result = await service.report_found_pet(user_id, payload)
        assert getattr(result, "is_duplicate", False) is False
        mock_repo.create_found_report.assert_awaited_once()

    # ── TEST E: Lost vs Found isolation ─────────────────────────────────
    @pytest.mark.asyncio
    async def test_lost_and_found_duplicate_isolation(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.find_active_lost_duplicate.return_value = None
        new_lost = LostReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            pet_name="Bruno",
            breed="labrador",
            color="golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.create_lost_report.return_value = new_lost
        mock_repo.get_lost_report_by_id.return_value = new_lost

        lost_payload = LostReportCreate(
            species=Species.DOG,
            pet_name="Bruno",
            breed="Labrador",
            color="Golden",
            location_address="Banjara Hills Rd 12",
            lost_at=datetime.now(UTC),
        )
        await service.report_lost_pet(user_id, lost_payload)
        mock_repo.find_active_lost_duplicate.assert_awaited_once()
        mock_repo.find_active_found_duplicate.assert_not_called()

        mock_repo.reset_mock()
        mock_repo.find_active_found_duplicate.return_value = None
        new_found = FoundReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            breed_observed="labrador",
            color_observed="golden",
            location_address="Banjara Hills Rd 12",
            found_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
            created_at=datetime.now(UTC),
            user=None,
            media=[],
        )
        mock_repo.create_found_report.return_value = new_found
        mock_repo.get_found_report_by_id.return_value = new_found

        found_payload = FoundReportCreate(
            species=Species.DOG,
            breed_observed="Labrador",
            color_observed="Golden",
            location_address="Banjara Hills Rd 12",
            found_at=datetime.now(UTC),
        )
        await service.report_found_pet(user_id, found_payload)
        mock_repo.find_active_found_duplicate.assert_awaited_once()
        mock_repo.find_active_lost_duplicate.assert_not_called()


class TestLostFoundDuplicateRouterContract:
    """HTTP router endpoint tests asserting status code 201 and is_duplicate boolean value in response."""

    @pytest.mark.asyncio
    async def test_router_lost_report_first_submission_and_duplicate(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from pawguard.core.security import AccessTokenClaims
        from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
        from pawguard.modules.lost_found.router import get_lost_found_service, router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_user_obj = User(
            id=user_id,
            email="owner@example.com",
            full_name="Pet Owner",
            phone="+919876543210",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
            mfa_enabled=False,
            created_at=now,
            updated_at=now,
        )
        mock_user = CurrentUser(
            user=mock_user_obj,
            claims=AccessTokenClaims(
                user_id=user_id,
                session_id=uuid.uuid4(),
                roles=["pet_owner"],
                jti=str(uuid.uuid4()),
                expires_at=datetime.now(UTC),
            ),
            db=AsyncMock(),
            redis=AsyncMock(),
        )

        mock_svc = AsyncMock(spec=LostFoundService)
        first_report = LostReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            pet_name="Charlie",
            breed="golden retriever",
            color="golden",
            location_address="Sector 4",
            lost_at=now,
            status=ReportStatus.ACTIVE,
            created_at=now,
            user=None,
            media=[],
        )
        first_report._is_duplicate = False
        first_report.is_duplicate = False
        mock_svc.report_lost_pet.return_value = first_report

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_lost_found_service] = lambda: mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.post(
                "/api/v1/lost-found/lost",
                json={
                    "species": "dog",
                    "pet_name": "Charlie",
                    "breed": "Golden Retriever",
                    "color": "Golden",
                    "location_address": "Sector 4",
                    "lost_at": now.isoformat(),
                },
            )
            assert resp1.status_code == 201
            data1 = resp1.json()["data"]
            assert data1["is_duplicate"] is False
            assert data1["id"] == str(first_report.id)

            # Second submission: sequential duplicate
            dup_report = LostReport(
                id=first_report.id,
                user_id=user_id,
                species=Species.DOG,
                pet_name="Charlie",
                breed="golden retriever",
                color="golden",
                location_address="Sector 4",
                lost_at=now,
                status=ReportStatus.ACTIVE,
                created_at=now,
                user=None,
                media=[],
            )
            dup_report._is_duplicate = True
            dup_report.is_duplicate = True
            mock_svc.report_lost_pet.return_value = dup_report

            resp2 = await client.post(
                "/api/v1/lost-found/lost",
                json={
                    "species": "dog",
                    "pet_name": "Charlie",
                    "breed": "Golden Retriever",
                    "color": "Golden",
                    "location_address": "Sector 4",
                    "lost_at": now.isoformat(),
                },
            )
            assert resp2.status_code == 201
            data2 = resp2.json()["data"]
            assert data2["is_duplicate"] is True
            assert data2["id"] == str(first_report.id)

    @pytest.mark.asyncio
    async def test_router_found_report_first_submission_and_duplicate(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from pawguard.core.security import AccessTokenClaims
        from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
        from pawguard.modules.lost_found.router import get_lost_found_service, router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_user_obj = User(
            id=user_id,
            email="finder@example.com",
            full_name="Pet Finder",
            phone="+919876543211",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
            mfa_enabled=False,
            created_at=now,
            updated_at=now,
        )
        mock_user = CurrentUser(
            user=mock_user_obj,
            claims=AccessTokenClaims(
                user_id=user_id,
                session_id=uuid.uuid4(),
                roles=["pet_owner"],
                jti=str(uuid.uuid4()),
                expires_at=datetime.now(UTC),
            ),
            db=AsyncMock(),
            redis=AsyncMock(),
        )

        mock_svc = AsyncMock(spec=LostFoundService)
        first_report = FoundReport(
            id=uuid.uuid4(),
            user_id=user_id,
            species=Species.DOG,
            breed_observed="husky",
            color_observed="grey",
            location_address="Sector 9",
            found_at=now,
            status=ReportStatus.ACTIVE,
            created_at=now,
            user=None,
            media=[],
        )
        first_report._is_duplicate = False
        first_report.is_duplicate = False
        mock_svc.report_found_pet.return_value = first_report

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_lost_found_service] = lambda: mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.post(
                "/api/v1/lost-found/found",
                json={
                    "species": "dog",
                    "breed_observed": "Husky",
                    "color_observed": "Grey",
                    "location_address": "Sector 9",
                    "found_at": now.isoformat(),
                },
            )
            assert resp1.status_code == 201
            data1 = resp1.json()["data"]
            assert data1["is_duplicate"] is False
            assert data1["id"] == str(first_report.id)

            # Second submission: sequential duplicate
            dup_report = FoundReport(
                id=first_report.id,
                user_id=user_id,
                species=Species.DOG,
                breed_observed="husky",
                color_observed="grey",
                location_address="Sector 9",
                found_at=now,
                status=ReportStatus.ACTIVE,
                created_at=now,
                user=None,
                media=[],
            )
            dup_report._is_duplicate = True
            dup_report.is_duplicate = True
            mock_svc.report_found_pet.return_value = dup_report

            resp2 = await client.post(
                "/api/v1/lost-found/found",
                json={
                    "species": "dog",
                    "breed_observed": "Husky",
                    "color_observed": "Grey",
                    "location_address": "Sector 9",
                    "found_at": now.isoformat(),
                },
            )
            assert resp2.status_code == 201
            data2 = resp2.json()["data"]
            assert data2["is_duplicate"] is True
            assert data2["id"] == str(first_report.id)
