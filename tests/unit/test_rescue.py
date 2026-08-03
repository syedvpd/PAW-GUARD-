"""Unit tests for RescueService with mocked repository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from pawguard.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.fleet.models import VehicleStatus
from pawguard.modules.rescue.models import (
    RescueDispatch,
    RescueEscalationType,
    RescueFailureReason,
    RescuePhysicalCondition,
    RescueRequest,
    RescueSeverity,
    RescueStatus,
)
from pawguard.modules.rescue.repository import RescueRepository
from pawguard.modules.rescue.schemas import RescueDispatchResponse, RescueRequestCreate
from pawguard.modules.rescue.service import RescueService
from pawguard.services.audit_service import AuditService


class TestRescueService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=RescueRepository)
        repo._session = AsyncMock()
        # Fast-path ticket-existence check returns None (free) by default so
        # the retry loop proceeds straight to create_request.
        repo.get_request_by_ticket.return_value = None
        # Public status lookup returns None (not found) by default.
        repo.get_request_by_ticket_and_phone.return_value = None
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
            location_address="123 Main St", physical_condition=RescuePhysicalCondition.INJURED,
            status=RescueStatus.REPORTED,
        )
        result = await service.report_incident(
            reporter_name="John", reporter_phone="+1234567890",
            location_address="123 Main St", physical_condition=RescuePhysicalCondition.INJURED,
            actor_id=uuid.uuid4(),
        )
        assert result.ticket_number.startswith("RES-")
        assert result.status == RescueStatus.REPORTED

    @pytest.mark.asyncio
    async def test_report_incident_anonymous_still_audited(self, service, mock_repo, mock_audit):
        """Anonymous (actor_id=None) public reports must still be audited with
        the reporter IP - the public intake is the highest-abuse surface."""
        request_id = uuid.uuid4()
        mock_repo.create_request.return_value = None
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=request_id, ticket_number="RES-20260730-9999",
            reporter_name="Anonymous", reporter_phone="+1000000000",
            location_address="Unknown", physical_condition=RescuePhysicalCondition.INJURED,
            status=RescueStatus.REPORTED, is_anonymous=True,
        )
        await service.report_incident(
            reporter_name="Anonymous", reporter_phone="+1000000000",
            location_address="Unknown", physical_condition=RescuePhysicalCondition.INJURED,
            is_anonymous=True, actor_id=None, ip_address="203.0.113.9",
        )
        mock_audit.record.assert_awaited_once()
        kwargs = mock_audit.record.call_args.kwargs
        assert kwargs["event_type"].value == "rescue_reported"
        assert kwargs["actor_id"] is None
        assert kwargs["ip_address"] == "203.0.113.9"
        assert kwargs["metadata"]["is_anonymous"] is True

    @pytest.mark.asyncio
    async def test_verify_request_approve(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None
        result = await service.dispatch_team(request_id, assigned_driver_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert result.status == RescueStatus.DISPATCHED
        # The in-memory relationship must be set so the dispatch endpoint
        # response serializes the dispatch instead of None (identity-map
        # re-fetch does not overwrite the already-loaded None).
        assert result.dispatch is not None
        assert result.dispatch.rescue_request_id == request_id

    @pytest.mark.asyncio
    async def test_dispatch_team_stores_escalation(self, service, mock_repo):
        """Escalation Protocol request flows to the dispatch record (M-D)."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None
        await service.dispatch_team(
            request_id,
            escalation_type=RescueEscalationType.LAW_ENFORCEMENT,
            escalation_notes="Aggressive dog, need police support",
            actor_id=uuid.uuid4(),
        )
        created = mock_repo.create_dispatch.call_args[0][0]
        assert created.escalation_type == RescueEscalationType.LAW_ENFORCEMENT
        assert created.escalation_notes == "Aggressive dog, need police support"

    @pytest.mark.asyncio
    async def test_dispatch_team_no_escalation_by_default(self, service, mock_repo):
        """Unset escalation stays None on the dispatch record (M-D)."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None
        await service.dispatch_team(request_id, actor_id=uuid.uuid4())
        created = mock_repo.create_dispatch.call_args[0][0]
        assert created.escalation_type is None
        assert created.escalation_notes is None

    @pytest.mark.asyncio
    @patch("pawguard.modules.rescue.service.FleetService")
    async def test_dispatch_team_auto_checks_out_equipment(self, mock_fleet_cls, service, mock_repo):
        """Equipment named on the dispatch is auto-checked-out against the
        dispatch and linked to the assigned driver (PRR 3.3)."""
        request_id = uuid.uuid4()
        driver_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.side_effect = lambda d: d

        mock_fleet = AsyncMock()
        mock_fleet_cls.return_value = mock_fleet

        result = await service.dispatch_team(
            request_id,
            assigned_driver_id=driver_id,
            equipment_details="Net Gun, Crate\nTrap; Blanket",
            actor_id=uuid.uuid4(),
        )
        assert result.status == RescueStatus.DISPATCHED
        created_dispatch = mock_repo.create_dispatch.call_args[0][0]
        mock_fleet.checkout_equipment_for_dispatch.assert_awaited_once()
        kwargs = mock_fleet.checkout_equipment_for_dispatch.call_args.kwargs
        assert kwargs["rescue_dispatch_id"] == created_dispatch.id
        assert kwargs["equipment_names"] == ["Net Gun", "Crate", "Trap", "Blanket"]
        assert kwargs["assigned_to_agent_id"] == driver_id

    @pytest.mark.asyncio
    @patch("pawguard.modules.rescue.service.FleetService")
    async def test_dispatch_team_no_equipment_skips_checkout(self, mock_fleet_cls, service, mock_repo):
        """A dispatch with no equipment_details creates no checkout rows."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None

        mock_fleet = AsyncMock()
        mock_fleet_cls.return_value = mock_fleet

        await service.dispatch_team(request_id, actor_id=uuid.uuid4())

        mock_fleet.checkout_equipment_for_dispatch.assert_not_called()

    @pytest.mark.asyncio
    @patch("pawguard.modules.rescue.service.FleetService")
    async def test_update_dispatch_status_admitted_releases_equipment(self, mock_fleet_cls, service, mock_repo):
        """Marking a rescue ADMITTED releases the dispatched equipment (PRR 3.3)."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.RESCUED, reports=[],
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch
        mock_repo.create_report.return_value = None

        mock_fleet = AsyncMock()
        mock_fleet_cls.return_value = mock_fleet

        result = await service.update_dispatch_status(
            request_id, status=RescueStatus.ADMITTED, agent_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
        )
        assert result.status == RescueStatus.ADMITTED
        mock_fleet.release_equipment_for_dispatch.assert_awaited_once()
        release_kwargs = mock_fleet.release_equipment_for_dispatch.call_args.kwargs
        assert release_kwargs["rescue_dispatch_id"] == dispatch.id

    @pytest.mark.asyncio
    @patch("pawguard.modules.rescue.service.FleetService")
    async def test_update_dispatch_status_failed_releases_equipment(self, mock_fleet_cls, service, mock_repo):
        """A failed (REJECTED) rescue releases the dispatched equipment too."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.DISPATCHED,
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch

        mock_fleet = AsyncMock()
        mock_fleet_cls.return_value = mock_fleet

        result = await service.update_dispatch_status(
            request_id, status=RescueStatus.REJECTED, agent_id=uuid.uuid4(),
            failure_reason="Animal fled", actor_id=uuid.uuid4(),
        )
        assert result.status == RescueStatus.VERIFIED
        mock_fleet.release_equipment_for_dispatch.assert_awaited_once()
        assert (
            mock_fleet.release_equipment_for_dispatch.call_args.kwargs["rescue_dispatch_id"]
            == dispatch.id
        )

    def test_parse_equipment_details(self):
        from pawguard.modules.rescue.service import _parse_equipment_details

        assert _parse_equipment_details("Net Gun, Crate\nTrap; Blanket") == [
            "Net Gun", "Crate", "Trap", "Blanket",
        ]
        assert _parse_equipment_details("  Net Gun  ,,  Crate  ") == ["Net Gun", "Crate"]
        assert _parse_equipment_details("") == []
        assert _parse_equipment_details(None) == []


    @pytest.mark.asyncio
    async def test_dispatch_team_already_dispatched(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
        assert dispatch.failed_at is not None
        # Canonical PRR 3.3 outcome code stored, not free text.
        assert dispatch.failure_reason == RescueFailureReason.ANIMAL_FLED.value

    @pytest.mark.asyncio
    async def test_update_dispatch_status_fail_normalises_legacy_reason(
        self, service, mock_repo
    ):
        """Legacy free-text reasons map to the canonical outcome code (M-1)."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.DISPATCHED,
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch
        await service.update_dispatch_status(
            request_id, status=RescueStatus.REJECTED, agent_id=uuid.uuid4(),
            failure_reason="Area Inaccessible", actor_id=uuid.uuid4(),
        )
        assert dispatch.failure_reason == RescueFailureReason.AREA_INACCESSIBLE.value

    @pytest.mark.asyncio
    async def test_update_dispatch_status_fail_unknown_reason_falls_back_to_other(
        self, service, mock_repo
    ):
        """Unrecognised reasons fall back to OTHER so a field agent can always
        log a failed rescue (M-1)."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.DISPATCHED,
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch
        await service.update_dispatch_status(
            request_id, status=RescueStatus.REJECTED, agent_id=uuid.uuid4(),
            failure_reason="Animal not found", actor_id=uuid.uuid4(),
        )
        assert dispatch.failure_reason == RescueFailureReason.OTHER.value

    @pytest.mark.asyncio
    async def test_update_dispatch_status_fail_defaults_to_other(
        self, service, mock_repo
    ):
        """Missing reason stores OTHER instead of a free-text default (M-1)."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.DISPATCHED,
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = dispatch
        await service.update_dispatch_status(
            request_id, status=RescueStatus.REJECTED, agent_id=uuid.uuid4(), actor_id=uuid.uuid4(),
        )
        assert dispatch.failure_reason == RescueFailureReason.OTHER.value

    @pytest.mark.asyncio
    async def test_get_request_found(self, service, mock_repo):
        request_id = uuid.uuid4()
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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
    async def test_lookup_public_status_found(self, service, mock_repo):
        """Public case-status lookup returns the reporter's own case (M-E)."""
        now = datetime.now(UTC)
        mock_repo.get_request_by_ticket_and_phone.return_value = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-1234",
            reporter_name="J", reporter_phone="+1111111111",
            location_address="A", physical_condition=RescuePhysicalCondition.INJURED,
            severity=RescueSeverity.HIGH, animal_count=1,
            status=RescueStatus.DISPATCHED,
            created_at=now, updated_at=now,
        )
        result = await service.lookup_public_status("RES-20260730-1234", "+1111111111")
        assert result.ticket_number == "RES-20260730-1234"
        assert result.status == RescueStatus.DISPATCHED
        assert result.severity == RescueSeverity.HIGH
        assert result.animal_count == 1
        # No reporter PII in the public response.
        assert not hasattr(result, "reporter_name")
        assert not hasattr(result, "reporter_phone")

    @pytest.mark.asyncio
    async def test_lookup_public_status_not_found(self, service, mock_repo):
        """Wrong ticket or wrong phone yields the same NotFoundError - no
        case data leaks to someone guessing a ticket number (M-E)."""
        mock_repo.get_request_by_ticket_and_phone.return_value = None
        with pytest.raises(NotFoundError, match="Rescue request not found"):
            await service.lookup_public_status("RES-00000000-0000", "+9999999999")

    @pytest.mark.asyncio
    async def test_lookup_public_status_requires_matching_phone(self, service, mock_repo):
        """The repo lookup is keyed on ticket AND phone so a mismatched phone
        never resolves the case - and a non-matching phone surfaces the same
        NotFoundError as an unknown ticket (M-E)."""
        with pytest.raises(NotFoundError, match="Rescue request not found"):
            await service.lookup_public_status("RES-20260730-1234", "+9999999999")
        mock_repo.get_request_by_ticket_and_phone.assert_awaited_once_with(
            "RES-20260730-1234", "+9999999999"
        )

    @pytest.mark.asyncio
    async def test_list_requests_paginated(self, service, mock_repo):
        now = datetime.now(UTC)
        req = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-001", reporter_name="A",
            reporter_phone="+12345", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED, is_anonymous=False, animal_count=1,
            severity=RescueSeverity.MEDIUM, is_urgent=False,
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
            reporter_phone="+1", location_address="Addr", physical_condition=RescuePhysicalCondition.UNKNOWN,
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

    # --- Bulk status update: state-machine enforcement (H-1) ---

    @pytest.mark.asyncio
    async def test_bulk_update_status_legal_transition(self, service, mock_repo, mock_audit):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED,
        )
        mock_repo.list_by_ids.return_value = [request]
        updated = await service.bulk_update_status(
            [request_id], RescueStatus.VERIFIED, actor_id=uuid.uuid4()
        )
        assert updated == 1
        assert request.status == RescueStatus.VERIFIED
        mock_audit.record.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bulk_update_status_blocks_illegal_jump(self, service, mock_repo):
        """REPORTED -> ADMITTED must be rejected, not silently applied."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED,
        )
        mock_repo.list_by_ids.return_value = [request]
        with pytest.raises(ConflictError, match="not in a state"):
            await service.bulk_update_status(
                [request_id], RescueStatus.ADMITTED, actor_id=uuid.uuid4()
            )
        # Nothing changed.
        assert request.status == RescueStatus.REPORTED
        mock_repo._session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bulk_update_status_blocks_rejected(self, service, mock_repo):
        """Bulk REJECTED is ambiguous (rationale vs failure reason) - blocked."""
        mock_repo.list_by_ids.return_value = []
        with pytest.raises(ValidationFailedError, match="Bulk REJECTED"):
            await service.bulk_update_status(
                [uuid.uuid4()], RescueStatus.REJECTED, actor_id=uuid.uuid4()
            )

    @pytest.mark.asyncio
    async def test_bulk_update_status_admitted_creates_dog_profile(
        self, service, mock_repo, mock_dog_repo
    ):
        """Bulk ADMITTED must mirror the single-request side effects."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-20260730-0001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.RESCUED, reports=[],
        )
        dispatch = RescueDispatch(rescue_request_id=request_id)
        request.dispatch = dispatch
        mock_repo.list_by_ids.return_value = [request]
        mock_repo.create_report.return_value = None

        updated = await service.bulk_update_status(
            [request_id], RescueStatus.ADMITTED, actor_id=uuid.uuid4()
        )
        assert updated == 1
        assert request.status == RescueStatus.ADMITTED
        assert dispatch.admitted_at is not None
        mock_repo.create_report.assert_awaited_once()
        mock_dog_repo.create.assert_awaited_once()
        created_dog = mock_dog_repo.create.call_args[0][0]
        assert created_dog.rescue_case_id == request_id
        assert created_dog.registration_number.startswith("DOG-")

    @pytest.mark.asyncio
    async def test_bulk_update_status_dispatch_creates_dispatch_record(
        self, service, mock_repo
    ):
        """Bulk DISPATCHED must create the dispatch row the lifecycle needs."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.list_by_ids.return_value = [request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None

        updated = await service.bulk_update_status(
            [request_id], RescueStatus.DISPATCHED, actor_id=uuid.uuid4()
        )
        assert updated == 1
        assert request.status == RescueStatus.DISPATCHED
        mock_repo.create_dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bulk_update_status_not_found(self, service, mock_repo):
        mock_repo.list_by_ids.return_value = []
        with pytest.raises(NotFoundError, match="No rescue requests"):
            await service.bulk_update_status(
                [uuid.uuid4()], RescueStatus.VERIFIED, actor_id=uuid.uuid4()
            )

    # --- RescuePhysicalCondition enum (H-2) ---

    @pytest.mark.asyncio
    async def test_report_incident_stores_severity_and_urgent(self, service, mock_repo):
        """Intake severity / urgent flag flow through to the created request
        (PRR 3.2 severity prioritization + PRR 3.1.1 banner flag, M-A)."""
        mock_repo.create_request.return_value = None
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-7777",
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.CRITICAL,
            severity=RescueSeverity.CRITICAL, is_urgent=True,
            status=RescueStatus.REPORTED,
        )
        await service.report_incident(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.CRITICAL,
            severity=RescueSeverity.CRITICAL, is_urgent=True,
        )
        created = mock_repo.create_request.call_args[0][0]
        assert created.severity == RescueSeverity.CRITICAL
        assert created.is_urgent is True

    @pytest.mark.asyncio
    async def test_report_incident_defaults_severity_medium(self, service, mock_repo):
        """Unset severity defaults to MEDIUM on intake (M-A)."""
        mock_repo.create_request.return_value = None
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-7778",
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED,
        )
        await service.report_incident(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
        )
        created = mock_repo.create_request.call_args[0][0]
        assert created.severity == RescueSeverity.MEDIUM
        assert created.is_urgent is False

    @pytest.mark.asyncio
    async def test_verify_request_updates_severity_and_urgent(self, service, mock_repo):
        """Coordinators refine severity / urgent flag at verification (M-A)."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            severity=RescueSeverity.MEDIUM, is_urgent=False,
            status=RescueStatus.REPORTED,
        )
        mock_repo.get_request_by_id.return_value = request
        result = await service.verify_request(
            request_id, approve=True,
            severity=RescueSeverity.CRITICAL, is_urgent=True,
            actor_id=uuid.uuid4(),
        )
        assert result.severity == RescueSeverity.CRITICAL
        assert result.is_urgent is True
        assert result.status == RescueStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_list_requests_paginated_forwards_severity_filters(
        self, service, mock_repo
    ):
        """Severity / urgent filters reach the repository (M-A)."""
        now = datetime.now(UTC)
        req = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-001", reporter_name="A",
            reporter_phone="+12345", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            severity=RescueSeverity.HIGH, is_urgent=True,
            status=RescueStatus.REPORTED, is_anonymous=False, animal_count=1,
            created_at=now, updated_at=now,
        )
        mock_repo.list_paginated.return_value = ([req], 1)
        result = await service.list_requests_paginated(
            PageParams(page=1, page_size=20), SortParams(),
            severity=RescueSeverity.HIGH, urgent_only=True,
        )
        assert result.meta.total == 1
        mock_repo.list_paginated.assert_awaited_once()
        kwargs = mock_repo.list_paginated.call_args.kwargs
        assert kwargs["severity"] == RescueSeverity.HIGH
        assert kwargs["urgent_only"] is True

    @pytest.mark.asyncio
    async def test_report_incident_stores_media_evidence(self, service, mock_repo):
        """Intake media object keys flow through to the created request (M-B)."""
        media = ["rescue/2026/08/photo_1.jpg", "rescue/2026/08/clip_2.mp4"]
        mock_repo.create_request.return_value = None
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-8888",
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.INJURED,
            status=RescueStatus.REPORTED, media_evidence=media,
        )
        await service.report_incident(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.INJURED,
            media_evidence=media,
        )
        created = mock_repo.create_request.call_args[0][0]
        assert created.media_evidence == media

    @pytest.mark.asyncio
    async def test_report_incident_audit_records_media_count(
        self, service, mock_repo, mock_audit
    ):
        """The intake audit metadata records how many media items were attached (M-B)."""
        mock_repo.create_request.return_value = None
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-8889",
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.INJURED,
            status=RescueStatus.REPORTED,
        )
        await service.report_incident(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.INJURED,
            media_evidence=["rescue/2026/08/photo_1.jpg"],
            actor_id=None, ip_address="203.0.113.10",
        )
        mock_audit.record.assert_awaited_once()
        assert mock_audit.record.call_args.kwargs["metadata"]["media_count"] == 1

    @pytest.mark.asyncio
    async def test_report_incident_stores_environmental_factors_and_notes(
        self, service, mock_repo
    ):
        """Environmental factors + reporter notes flow through to the created
        request (PRR 3.2 Temporal Tracking, M-C)."""
        mock_repo.create_request.return_value = None
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-8890",
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.INJURED,
            environmental_factors="Heavy rain", reporter_notes="Timid dog",
            status=RescueStatus.REPORTED,
        )
        await service.report_incident(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.INJURED,
            environmental_factors="Heavy rain", reporter_notes="Timid dog",
        )
        created = mock_repo.create_request.call_args[0][0]
        assert created.environmental_factors == "Heavy rain"
        assert created.reporter_notes == "Timid dog"

    @pytest.mark.asyncio
    async def test_report_incident_stores_enum_value(self, service, mock_repo):
        request_id = uuid.uuid4()
        mock_repo.create_request.return_value = None
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=request_id, ticket_number="RES-20260730-5555",
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.CRITICAL,
            status=RescueStatus.REPORTED,
        )
        result = await service.report_incident(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.CRITICAL,
        )
        assert result.physical_condition == RescuePhysicalCondition.CRITICAL

    # --- Ticket-number collision retry (M-2) ---

    @pytest.mark.asyncio
    async def test_report_incident_retries_on_collision(self, service, mock_repo):
        """A taken ticket is skipped via the fast-path check, then a fresh
        ticket is allocated and the request is created once."""
        existing = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-1234",
            reporter_name="Old", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED,
        )
        mock_repo.get_request_by_ticket.side_effect = [existing, None]
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-5678",
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED,
        )
        result = await service.report_incident(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
        )
        assert result is not None
        # create_request must be called exactly once, with a free ticket.
        mock_repo.create_request.assert_awaited_once()
        created = mock_repo.create_request.call_args[0][0]
        assert created.ticket_number != existing.ticket_number
        assert created.ticket_number.startswith("RES-")

    @pytest.mark.asyncio
    async def test_report_incident_retries_on_integrity_error(self, service, mock_repo):
        """A concurrent duplicate that slips past the fast-path check is
        caught by the IntegrityError handler, rolled back, and retried."""
        mock_repo.create_request.side_effect = [
            IntegrityError("INSERT INTO rescue_requests ...", {}, Exception("duplicate")),
            None,
        ]
        mock_repo.get_request_by_id.return_value = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-9999",
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED,
        )
        result = await service.report_incident(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
        )
        assert result is not None
        assert mock_repo.create_request.await_count == 2
        mock_repo._session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_report_incident_raises_conflict_after_exhausting_retries(
        self, service, mock_repo
    ):
        """If every candidate ticket is taken, a clean ConflictError is raised
        instead of a 500, and nothing is persisted."""
        taken = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-20260730-0000",
            reporter_name="Old", reporter_phone="+1", location_address="A",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED,
        )
        mock_repo.get_request_by_ticket.return_value = taken  # always taken

        with pytest.raises(ConflictError, match="unique rescue ticket number"):
            await service.report_incident(
                reporter_name="J", reporter_phone="+1", location_address="A",
                physical_condition=RescuePhysicalCondition.UNKNOWN,
            )
        mock_repo.create_request.assert_not_awaited()


    # --- Multi-agent dispatch (PRR 3.2) ---

    @pytest.mark.asyncio
    async def test_dispatch_team_multi_agent(self, service, mock_repo):
        """Multiple agents plus the legacy driver are all mirrored into
        the dispatch-agent association table and deduplicated."""
        request_id = uuid.uuid4()
        driver_id = uuid.uuid4()
        agent_a = uuid.uuid4()
        agent_b = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None

        await service.dispatch_team(
            request_id,
            assigned_driver_id=driver_id,
            assigned_agent_ids=[agent_a, agent_b],
            actor_id=uuid.uuid4(),
        )

        assert mock_repo.create_dispatch_agent.call_count == 3
        created_agents = [
            call[0][0] for call in mock_repo.create_dispatch_agent.call_args_list
        ]
        agent_ids = {a.agent_id for a in created_agents}
        assert driver_id in agent_ids
        assert agent_a in agent_ids
        assert agent_b in agent_ids

    @pytest.mark.asyncio
    async def test_dispatch_team_driver_also_in_agent_table(self, service, mock_repo):
        """The legacy assigned_driver_id is mirrored into the dispatch-agent
        association table so the "assigned to me" filter works for drivers."""
        request_id = uuid.uuid4()
        driver_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None

        await service.dispatch_team(
            request_id,
            assigned_driver_id=driver_id,
            actor_id=uuid.uuid4(),
        )

        assert mock_repo.create_dispatch_agent.call_count == 1
        created_agent = mock_repo.create_dispatch_agent.call_args[0][0]
        assert created_agent.agent_id == driver_id

    # --- Vehicle assignment validation (PRR 3.2) ---

    @pytest.mark.asyncio
    @patch("pawguard.modules.rescue.service.FleetService")
    async def test_dispatch_team_rejects_inactive_vehicle(
        self, mock_fleet_cls, service, mock_repo
    ):
        """Only ACTIVE vehicles can be assigned to a dispatch."""
        request_id = uuid.uuid4()
        vehicle_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None

        mock_fleet = AsyncMock()
        mock_fleet_cls.return_value = mock_fleet
        mock_fleet.get_vehicle.return_value = AsyncMock(
            status=VehicleStatus.IN_MAINTENANCE
        )

        with pytest.raises(ValidationFailedError, match="ACTIVE"):
            await service.dispatch_team(
                request_id,
                assigned_vehicle_id=vehicle_id,
                actor_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    @patch("pawguard.modules.rescue.service.FleetService")
    async def test_dispatch_team_accepts_active_vehicle(
        self, mock_fleet_cls, service, mock_repo
    ):
        """An ACTIVE vehicle is accepted and stored on the dispatch."""
        request_id = uuid.uuid4()
        vehicle_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.VERIFIED,
        )
        mock_repo.get_request_by_id.side_effect = [request, request]
        mock_repo.get_dispatch_by_request_id.return_value = None
        mock_repo.create_dispatch.return_value = None

        mock_fleet = AsyncMock()
        mock_fleet_cls.return_value = mock_fleet
        mock_fleet.get_vehicle.return_value = AsyncMock(status=VehicleStatus.ACTIVE)

        await service.dispatch_team(
            request_id,
            assigned_vehicle_id=vehicle_id,
            actor_id=uuid.uuid4(),
        )

        created_dispatch = mock_repo.create_dispatch.call_args[0][0]
        assert created_dispatch.assigned_vehicle_id == vehicle_id

    # --- assigned_to_me filter ---

    @pytest.mark.asyncio
    async def test_list_requests_paginated_forwards_assigned_to_me(
        self, service, mock_repo
    ):
        """assigned_to_me reaches the repository so the "my cases" filter
        is applied on the dispatch-agent association and driver column."""
        now = datetime.now(UTC)
        req = RescueRequest(
            id=uuid.uuid4(), ticket_number="RES-001", reporter_name="A",
            reporter_phone="+12345", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED, is_anonymous=False, animal_count=1,
            severity=RescueSeverity.MEDIUM, is_urgent=False,
            created_at=now, updated_at=now,
        )
        mock_repo.list_paginated.return_value = ([req], 1)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        user_id = uuid.uuid4()
        result = await service.list_requests_paginated(
            page, sort, assigned_to_me=user_id,
        )
        assert result.meta.total == 1
        mock_repo.list_paginated.assert_awaited_once()
        kwargs = mock_repo.list_paginated.call_args.kwargs
        assert kwargs["assigned_to_me"] == user_id

    # --- Escalation ---

    @pytest.mark.asyncio
    async def test_escalate_sets_escalation_on_dispatch(self, service, mock_repo):
        """Escalation type and notes are written to the dispatch record."""
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.DISPATCHED,
        )
        dispatch = RescueDispatch(
            rescue_request_id=request_id,
            escalation_type=None,
            escalation_notes=None,
        )
        mock_repo.get_request_by_id.return_value = request
        mock_repo.get_dispatch_by_request_id.return_value = dispatch

        result = await service.escalate(
            request_id,
            escalation_type=RescueEscalationType.BACKUP_PERSONNEL,
            escalation_notes="Second team needed",
            actor_id=uuid.uuid4(),
        )

        assert result.id == request_id
        assert dispatch.escalation_type == RescueEscalationType.BACKUP_PERSONNEL
        assert dispatch.escalation_notes == "Second team needed"

    @pytest.mark.asyncio
    async def test_escalate_not_found_request(self, service, mock_repo):
        mock_repo.get_request_by_id.return_value = None
        with pytest.raises(NotFoundError, match="Rescue request not found"):
            await service.escalate(
                uuid.uuid4(),
                escalation_type=RescueEscalationType.BACKUP_PERSONNEL,
            )

    @pytest.mark.asyncio
    async def test_escalate_not_found_dispatch(self, service, mock_repo):
        request_id = uuid.uuid4()
        request = RescueRequest(
            id=request_id, ticket_number="RES-001", reporter_name="A",
            reporter_phone="+1", location_address="Addr",
            physical_condition=RescuePhysicalCondition.UNKNOWN,
            status=RescueStatus.REPORTED,
        )
        mock_repo.get_request_by_id.return_value = request
        mock_repo.get_dispatch_by_request_id.return_value = None

        with pytest.raises(NotFoundError, match="Dispatch record not found"):
            await service.escalate(
                request_id,
                escalation_type=RescueEscalationType.BACKUP_PERSONNEL,
            )


class TestRescueRequestCreateSchema:
    """Physical-condition enum coercion: legacy labels accepted, canonical
    values accepted, unknown values rejected (H-2)."""

    def test_legacy_label_normalised(self) -> None:
        payload = RescueRequestCreate(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition="Injured/Fractured",
        )
        assert payload.physical_condition == RescuePhysicalCondition.INJURED

    def test_legacy_stray_label_normalised(self) -> None:
        payload = RescueRequestCreate(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition="Stray",
        )
        assert payload.physical_condition == RescuePhysicalCondition.ABANDONED

    def test_canonical_value_accepted(self) -> None:
        payload = RescueRequestCreate(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition="fractured_injured",
        )
        assert payload.physical_condition == RescuePhysicalCondition.INJURED

    def test_unknown_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RescueRequestCreate(
                reporter_name="J", reporter_phone="+1", location_address="A",
                physical_condition="Sparkly Unicorn",
            )

    def test_environmental_factors_and_notes_accepted(self) -> None:
        payload = RescueRequestCreate(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition="injured",
            environmental_factors="Flooding", reporter_notes="Friendly dog",
        )
        assert payload.environmental_factors == "Flooding"
        assert payload.reporter_notes == "Friendly dog"

    def test_environmental_factors_and_notes_none_by_default(self) -> None:
        payload = RescueRequestCreate(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition="injured",
        )
        assert payload.environmental_factors is None
        assert payload.reporter_notes is None

    def test_media_evidence_up_to_five_accepted(self) -> None:
        payload = RescueRequestCreate(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition="injured",
            media_evidence=[f"rescue/2026/08/p{i}.jpg" for i in range(5)],
        )
        assert len(payload.media_evidence) == 5

    def test_media_evidence_over_five_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at most 5 items"):
            RescueRequestCreate(
                reporter_name="J", reporter_phone="+1", location_address="A",
                physical_condition="injured",
                media_evidence=[f"rescue/2026/08/p{i}.jpg" for i in range(6)],
            )

    def test_media_evidence_empty_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot be empty"):
            RescueRequestCreate(
                reporter_name="J", reporter_phone="+1", location_address="A",
                physical_condition="injured", media_evidence=["   "],
            )

    def test_media_evidence_none_accepted(self) -> None:
        payload = RescueRequestCreate(
            reporter_name="J", reporter_phone="+1", location_address="A",
            physical_condition="injured",
        )
        assert payload.media_evidence is None


class TestRescueFailureReasonSchema:
    """Failure-reason normalisation: legacy labels map to canonical codes and
    unknown values fall back to OTHER (M-1)."""

    @staticmethod
    def _dispatch_response(failure_reason: str | None) -> RescueDispatchResponse:
        return RescueDispatchResponse(
            id=uuid.uuid4(),
            rescue_request_id=uuid.uuid4(),
            assigned_driver_id=None,
            vehicle_id=None,
            equipment_details=None,
            dispatched_at=datetime.now(UTC),
            located_at=None,
            rescued_at=None,
            admitted_at=None,
            failed_at=datetime.now(UTC),
            failure_reason=failure_reason,
            escalation_type=None,
            escalation_notes=None,
            notes=None,
        )

    def test_legacy_label_normalised(self) -> None:
        payload = self._dispatch_response("Animal Fled")
        assert payload.failure_reason == RescueFailureReason.ANIMAL_FLED

    def test_canonical_value_accepted(self) -> None:
        payload = self._dispatch_response("false_report")
        assert payload.failure_reason == RescueFailureReason.FALSE_REPORT

    def test_unknown_value_falls_back_to_other(self) -> None:
        payload = self._dispatch_response("Animal not found")
        assert payload.failure_reason == RescueFailureReason.OTHER

    def test_none_accepted(self) -> None:
        payload = self._dispatch_response(None)
        assert payload.failure_reason is None
