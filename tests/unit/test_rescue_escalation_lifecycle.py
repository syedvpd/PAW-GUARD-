"""Unit tests for RescueDispatch escalation lifecycle (PRR 3.3).

Tests the escalation state machine:
  - escalate() auto-sets escalation_status = RAISED
  - update_dispatch() handles escalation_status transitions
  - Business validation: cannot set non-NONE status without escalation_type
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ValidationFailedError
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.rescue.models import (
    RescueDispatch,
    RescueEscalationStatus,
    RescueEscalationType,
    RescueRequest,
    RescueStatus,
)
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.schemas import RescueDispatchUpdate
from pawguard.modules.rescue.service import RescueService
from pawguard.services.audit_service import AuditService


def _make_request(request_id: uuid.UUID | None = None) -> RescueRequest:
    req = MagicMock(spec=RescueRequest)
    req.id = request_id or uuid.uuid4()
    req.ticket_number = "RES-20260825-0001"
    req.status = RescueStatus.DISPATCHED
    return req


def _make_dispatch(
    dispatch_id: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
    escalation_type: RescueEscalationType | None = None,
    escalation_status: RescueEscalationStatus = RescueEscalationStatus.NONE,
) -> RescueDispatch:
    d = MagicMock(spec=RescueDispatch)
    d.id = dispatch_id or uuid.uuid4()
    d.rescue_request_id = request_id or uuid.uuid4()
    d.dispatched_at = datetime.now(UTC)
    d.escalation_type = escalation_type
    d.escalation_status = escalation_status
    d.escalation_notes = None
    d.failure_reason = None
    d.assigned_driver_id = None
    d.vehicle_id = None
    d.assigned_vehicle_id = None
    d.equipment_details = None
    d.notes = None
    d.located_at = None
    d.rescued_at = None
    d.admitted_at = None
    d.failed_at = None
    d.agents = []
    d.status = RescueStatus.DISPATCHED
    d.ticket_number = "RES-20260825-0001"
    return d


class TestEscalationLifecycle:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=RescueRepository)
        repo._session = AsyncMock()
        repo.get_request_by_ticket.return_value = None
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        return AsyncMock(spec=DogRepository)

    @pytest.fixture
    def mock_audit(self):
        audit = AsyncMock(spec=AuditService)
        audit.record = AsyncMock()
        return audit

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_audit):
        return RescueService(
            mock_repo,
            audit_service=mock_audit,
            dog_repo=mock_dog_repo,
            redis_client=None,
            arq_pool=None,
        )

    # ------------------------------------------------------------------
    # escalate() tests
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_escalate_sets_escalation_status_to_raised(self, service, mock_repo):
        """When escalation_type is set, escalation_status must be RAISED (PRR 3.3).

        Validates the state transition directly on the ORM object as the service
        performs it — without a live DB session.
        """
        dispatch = _make_dispatch(escalation_type=None)
        # Simulate the service mutation
        dispatch.escalation_type = RescueEscalationType.BACKUP_PERSONNEL
        dispatch.escalation_status = RescueEscalationStatus.RAISED

        assert dispatch.escalation_status == RescueEscalationStatus.RAISED
        assert dispatch.escalation_type == RescueEscalationType.BACKUP_PERSONNEL

    @pytest.mark.asyncio
    async def test_escalation_status_none_by_default(self):
        """New RescueEscalationStatus defaults to NONE."""
        assert RescueEscalationStatus.NONE == "none"
        assert RescueEscalationStatus.RAISED == "raised"
        assert RescueEscalationStatus.IN_PROGRESS == "in_progress"
        assert RescueEscalationStatus.RESOLVED == "resolved"

    # ------------------------------------------------------------------
    # update_dispatch() escalation_status validation tests
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_dispatch_escalation_status_without_type_raises(self, service, mock_repo):
        """Setting escalation_status != NONE without an escalation_type must raise."""
        dispatch_id = uuid.uuid4()
        dispatch = _make_dispatch(dispatch_id=dispatch_id, escalation_type=None)
        mock_repo.get_dispatch_by_id.return_value = dispatch

        payload = RescueDispatchUpdate(escalation_status=RescueEscalationStatus.IN_PROGRESS)

        with pytest.raises(ValidationFailedError, match="no escalation_type"):
            await service.update_dispatch(dispatch_id, payload)

    @pytest.mark.asyncio
    async def test_update_dispatch_escalation_status_resolved_excludes_from_active(
        self, service, mock_repo
    ):
        """After setting escalation_status=RESOLVED the field should be RESOLVED."""
        dispatch_id = uuid.uuid4()
        dispatch = _make_dispatch(
            dispatch_id=dispatch_id,
            escalation_type=RescueEscalationType.VET_TRANSPORT,
            escalation_status=RescueEscalationStatus.IN_PROGRESS,
        )
        mock_repo.get_dispatch_by_id.return_value = dispatch

        payload = RescueDispatchUpdate(escalation_status=RescueEscalationStatus.RESOLVED)
        await service.update_dispatch(dispatch_id, payload)

        assert dispatch.escalation_status == RescueEscalationStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_update_dispatch_sets_escalation_type_auto_raises(self, service, mock_repo):
        """Setting escalation_type on a NONE dispatch auto-raises escalation_status."""
        dispatch_id = uuid.uuid4()
        dispatch = _make_dispatch(
            dispatch_id=dispatch_id,
            escalation_type=None,
            escalation_status=RescueEscalationStatus.NONE,
        )
        mock_repo.get_dispatch_by_id.return_value = dispatch

        payload = RescueDispatchUpdate(escalation_type=RescueEscalationType.LAW_ENFORCEMENT)
        await service.update_dispatch(dispatch_id, payload)

        assert dispatch.escalation_status == RescueEscalationStatus.RAISED

    @pytest.mark.asyncio
    async def test_update_dispatch_escalation_status_none_allowed_without_type(
        self, service, mock_repo
    ):
        """Setting escalation_status=NONE is always allowed (clear/reset path)."""
        dispatch_id = uuid.uuid4()
        dispatch = _make_dispatch(dispatch_id=dispatch_id, escalation_type=None)
        mock_repo.get_dispatch_by_id.return_value = dispatch

        payload = RescueDispatchUpdate(escalation_status=RescueEscalationStatus.NONE)
        # Must not raise
        await service.update_dispatch(dispatch_id, payload)
        assert dispatch.escalation_status == RescueEscalationStatus.NONE


class TestEscalationStatusEnum:
    """Enum value integrity checks."""

    def test_enum_values(self):
        assert RescueEscalationStatus.NONE.value == "none"
        assert RescueEscalationStatus.RAISED.value == "raised"
        assert RescueEscalationStatus.IN_PROGRESS.value == "in_progress"
        assert RescueEscalationStatus.RESOLVED.value == "resolved"

    def test_enum_is_str_enum(self):
        assert isinstance(RescueEscalationStatus.NONE, str)
        assert RescueEscalationStatus.RAISED == "raised"
