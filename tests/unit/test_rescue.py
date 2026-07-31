"""Unit tests for RescueService with mocked repository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.rescue.models import RescueDispatch, RescueRequest, RescueStatus
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.service import RescueService
from pawguard.services.audit_service import AuditService


class TestRescueService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=RescueRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def mock_dog_repo(self):
        return AsyncMock(spec=DogRepository)

    @pytest.fixture
    def service(self, mock_repo, mock_audit, mock_dog_repo):
        return RescueService(mock_repo, mock_audit, dog_repo=mock_dog_repo)

    @pytest.mark.asyncio
    async def test_report_incident(self, service, mock_repo, mock_audit):
        request_id = uuid.uuid4()
        mock_repo.create_request.return_value = None
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=request_id, ticket_number="RES-20260730-1234",
            reporter_name="John", reporter_phone="+1234567890",
            location_address="123 Main St", physical_condition="Injured",
            status=RescueStatus.REPORTED,
        )
        result = await service.report_incident(
            reporter_name="John", reporter_phone="+1234567890",
            location_address="123 Main St", physical_condition="Injured",
            actor_id=uuid.uuid4(),
        )
        assert result.ticket_number.startswith("RES-")
        assert result.status == RescueStatus.REPORTED

    @pytest.mark.asyncio
    async def test_verify_request_approve(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.REPORTED,
        )
        mock_repo.get_request_by_id.return_value = request
        result = await service.verify_request(request_id, approve=True, actor_id=uuid.uuid4())
        assert result.status == RescueStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_verify_request_reject(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.REPORTED,
        )
        mock_repo.get_request_by_id.return_value = request
        result = await service.verify_request(request_id, approve=False, rationale="Duplicate", actor_id=uuid.uuid4())
        assert result.status == RescueStatus.REJECTED
        assert result.rejection_rationale == "Duplicate"

    @pytest.mark.asyncio
    async def test_verify_request_reject_requires_rationale(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.REPORTED,
        )
        mock_repo.get_request_by_id.return_value = request
        with pytest.raises(ValidationFailedError, match="rationale is required"):
            await service.verify_request(request_id, approve=False)

    @pytest.mark.asyncio
    async def test_verify_request_not_found(self, service, mock_repo):
        mock_repo.get_request_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.verify_request(uuid.uuid4(), approve=True)

    @pytest.mark.asyncio
    async def test_verify_request_wrong_status(self, service, mock_repo):
        request = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.DISPATCHED,
        )
        mock_repo.get_request_by_id.return_value = request
        with pytest.raises(ConflictError, match="Cannot verify"):
            await service.verify_request(uuid.uuid4(), approve=True)

    @pytest.mark.asyncio
    async def test_dispatch_team(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None
        result = await service.dispatch_team(request_id, assigned_driver_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert result.status == RescueStatus.DISPATCHED

    @pytest.mark.asyncio
    async def test_dispatch_team_already_dispatched(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.return_value = request
        mock_repo.get_dispatch_by_request_id.return_value = RescueDispatch(rescue_request_id=request_id)
        with pytest.raises(ConflictError, match="already exists"):
            await service.dispatch_team(request_id)

    @pytest.mark.asyncio
    async def test_update_dispatch_status_located(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.DISPATCHED,
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch
        result = await service.update_dispatch_status(request_id, status=RescueStatus.LOCATED, agent_id=uuid.uuid4())
        assert result.status == RescueStatus.LOCATED

    @pytest.mark.asyncio
    async def test_update_dispatch_status_admitted(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.RESCUED, reports=[],
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch
        mock_repo.create_report.return_value = None
        result = await service.update_dispatch_status(
            request_id, status=RescueStatus.ADMITTED, agent_id=uuid.uuid4(), actor_id=uuid.uuid4(),
        )
        assert result.status == RescueStatus.ADMITTED

    @pytest.mark.asyncio
    async def test_update_dispatch_status_admitted_auto_creates_dog(
        self, service, mock_repo, mock_dog_repo
    ):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-20260730-0001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.RESCUED, reports=[],
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch
        mock_repo.create_report.return_value = None
        await service.update_dispatch_status(
            request_id, status=RescueStatus.ADMITTED, agent_id=uuid.uuid4(), actor_id=uuid.uuid4(),
        )
        mock_dog_repo.create.assert_awaited_once()
        created_dog = mock_dog_repo.create.call_args[0][0]
        assert created_dog.rescue_case_id == request_id
        assert created_dog.registration_number.startswith("DOG-")

    @pytest.mark.asyncio
    async def test_update_dispatch_status_fail(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.DISPATCHED,
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch
        result = await service.update_dispatch_status(
            request_id, status=RescueStatus.REJECTED, agent_id=uuid.uuid4(),
            failure_reason="Animal fled", actor_id=uuid.uuid4(),
        )
        assert result.status == RescueStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_get_request_found(self, service, mock_repo):
        request_id = uuid.uuid4()
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.REPORTED,
        )
        result = await service.get_request(request_id)
        assert result.id == request_id

    @pytest.mark.asyncio
    async def test_get_request_not_found(self, service, mock_repo):
        mock_repo.get_request_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_request(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_requests_paginated(self, service, mock_repo):
        now = datetime.now(UTC)
        req = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-001", reporter_name="A",
            reporter_phone="+12345", location_address="Addr", physical_condition="OK",
            status=RescueStatus.REPORTED, is_anonymous=False, animal_count=1,
            created_at=now, updated_at=now,
        )
        mock_repo.list_paginated.return_value = ([req], 1)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_requests_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_request(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition="OK",
            status=RescueStatus.REPORTED,
        )
        mock_repo.get_request_by_id.return_value = request
        await service.soft_delete_request(request_id, actor_id=uuid.uuid4())
        assert request.deleted_at is not None

    @pytest.mark.asyncio
    async def test_soft_delete_request_not_found(self, service, mock_repo):
        mock_repo.get_request_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_request(uuid.uuid4())
