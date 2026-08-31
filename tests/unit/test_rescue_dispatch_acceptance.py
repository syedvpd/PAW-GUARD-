"""Unit tests for dispatch acceptance persistence and schema exposure."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.rescue.models import (
    RescueDispatch,
    RescueDispatchAgent,
    RescuePhysicalCondition,
    RescueRequest,
    RescueSeverity,
    RescueStatus,
)
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.schemas import (
    RescueDispatchAgentResponse,
    RescueDispatchResponse,
)
from pawguard.modules.rescue.service import RescueService
from pawguard.services.audit_service import AuditService


class TestRescueDispatchAcceptance:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=RescueRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return RescueService(mock_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_accept_dispatch_sets_accepted_at_on_driver_and_dispatch(
        self, service, mock_repo, mock_audit
    ):
        request_id = uuid.uuid4()
        driver_id = uuid.uuid4()
        now = datetime.now(UTC)

        request = RescueRequest(
            id=request_id,
            ticket_number="RES-2026-0001",
            reporter_name="Jane Doe",
            reporter_phone="+1555123456",
            location_address="123 Main St",
            animal_count=1,
            physical_condition=RescuePhysicalCondition.INJURED,
            severity=RescueSeverity.HIGH,
            status=RescueStatus.DISPATCHED,
            created_at=now,
            updated_at=now,
        )
        dispatch = RescueDispatch(
            id=uuid.uuid4(),
            rescue_request_id=request_id,
            assigned_driver_id=driver_id,
            dispatched_at=now,
            accepted_at=None,
            created_at=now,
            updated_at=now,
        )
        dispatch.agents = []
        request.dispatch = dispatch

        mock_repo.get_request_by_id.return_value = request
        mock_repo.get_dispatch_by_request_id.return_value = dispatch

        result = await service.accept_dispatch(
            request_id,
            agent_id=driver_id,
            ip_address="192.168.1.10",
        )

        assert dispatch.accepted_at is not None
        assert isinstance(dispatch.accepted_at, datetime)
        mock_repo._session.flush.assert_awaited()
        mock_audit.record.assert_awaited()
        assert result.id == request_id

    @pytest.mark.asyncio
    async def test_accept_dispatch_sets_accepted_at_on_team_agent(
        self, service, mock_repo, mock_audit
    ):
        request_id = uuid.uuid4()
        driver_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        now = datetime.now(UTC)

        request = RescueRequest(
            id=request_id,
            ticket_number="RES-2026-0002",
            reporter_name="John Smith",
            reporter_phone="+1555654321",
            location_address="456 Oak Ave",
            animal_count=1,
            physical_condition=RescuePhysicalCondition.SICK,
            severity=RescueSeverity.MEDIUM,
            status=RescueStatus.DISPATCHED,
            created_at=now,
            updated_at=now,
        )
        dispatch = RescueDispatch(
            id=uuid.uuid4(),
            rescue_request_id=request_id,
            assigned_driver_id=driver_id,
            dispatched_at=now,
            accepted_at=None,
            created_at=now,
            updated_at=now,
        )
        agent_record = RescueDispatchAgent(
            id=uuid.uuid4(),
            dispatch_id=dispatch.id,
            agent_id=agent_id,
            role="field_medic",
            accepted_at=None,
            created_at=now,
            updated_at=now,
        )
        dispatch.agents = [agent_record]
        request.dispatch = dispatch

        mock_repo.get_request_by_id.return_value = request
        mock_repo.get_dispatch_by_request_id.return_value = dispatch

        await service.accept_dispatch(
            request_id,
            agent_id=agent_id,
            ip_address="10.0.0.5",
        )

        assert agent_record.accepted_at is not None
        assert dispatch.accepted_at is not None
        mock_repo._session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_accept_dispatch_rejects_unassigned_user(self, service, mock_repo, mock_audit):
        request_id = uuid.uuid4()
        driver_id = uuid.uuid4()
        unassigned_id = uuid.uuid4()
        now = datetime.now(UTC)

        request = RescueRequest(
            id=request_id,
            ticket_number="RES-2026-0003",
            reporter_name="Alice",
            reporter_phone="+1555000000",
            location_address="789 Pine Rd",
            animal_count=1,
            physical_condition=RescuePhysicalCondition.CRITICAL,
            severity=RescueSeverity.CRITICAL,
            status=RescueStatus.DISPATCHED,
            created_at=now,
            updated_at=now,
        )
        dispatch = RescueDispatch(
            id=uuid.uuid4(),
            rescue_request_id=request_id,
            assigned_driver_id=driver_id,
            dispatched_at=now,
            accepted_at=None,
            created_at=now,
            updated_at=now,
        )
        dispatch.agents = []
        request.dispatch = dispatch

        mock_repo.get_request_by_id.return_value = request
        mock_repo.get_dispatch_by_request_id.return_value = dispatch

        with pytest.raises(ConflictError, match="Agent is not assigned to this dispatch."):
            await service.accept_dispatch(
                request_id,
                agent_id=unassigned_id,
            )

    @pytest.mark.asyncio
    async def test_accept_dispatch_not_found(self, service, mock_repo):
        mock_repo.get_request_by_id.return_value = None
        with pytest.raises(NotFoundError, match="Rescue request not found."):
            await service.accept_dispatch(
                uuid.uuid4(),
                agent_id=uuid.uuid4(),
            )

    def test_schema_serialization_includes_accepted_at(self):
        now = datetime.now(UTC)
        dispatch_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        agent_model = RescueDispatchAgent(
            id=uuid.uuid4(),
            dispatch_id=dispatch_id,
            agent_id=agent_id,
            role="lead_rescuer",
            accepted_at=now,
            created_at=now,
            updated_at=now,
        )

        agent_dto = RescueDispatchAgentResponse.model_validate(agent_model)
        assert agent_dto.accepted_at == now

        dispatch_model = RescueDispatch(
            id=dispatch_id,
            rescue_request_id=uuid.uuid4(),
            assigned_driver_id=agent_id,
            dispatched_at=now,
            accepted_at=now,
            created_at=now,
            updated_at=now,
        )
        dispatch_model.agents = [agent_model]

        dispatch_dto = RescueDispatchResponse.model_validate(dispatch_model)
        assert dispatch_dto.accepted_at == now
        assert len(dispatch_dto.agents) == 1
        assert dispatch_dto.agents[0].accepted_at == now
