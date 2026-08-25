"""Unit tests for GrievanceService with mocked repository."""

import uuid
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.modules.grievance.models import (
    GrievanceComment,
    GrievanceStatus,
    GrievanceTicket,
    ServiceFeedback,
)
from pawguard.modules.grievance.repository import GrievanceRepository
from pawguard.modules.grievance.schemas import (
    CommentCreate,
    GrievanceCreate,
    GrievanceEscalate,
    GrievanceListFilter,
    GrievanceUpdate,
    ServiceFeedbackCreate,
)
from pawguard.modules.grievance.service import GrievanceService
from pawguard.services.audit_service import AuditService


class TestGrievanceService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=GrievanceRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return GrievanceService(mock_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_submit_complaint(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        mock_repo.create_ticket.return_value = GrievanceTicket(
            id=ticket_id,
            reporter_name="John",
            reporter_phone="+1234567890",
            complaint_type="service",
            details="Bad experience",
            status=GrievanceStatus.OPEN,
        )
        payload = GrievanceCreate(
            reporter_name="John",
            reporter_phone="+1234567890",
            complaint_type="service",
            details="Bad experience",
        )
        result = await service.submit_complaint(payload)
        assert result.status == GrievanceStatus.OPEN
        # SLA deadline is computed and passed to the created ticket.
        created_kwargs = mock_repo.create_ticket.call_args[0][0]
        assert created_kwargs.sla_due_at is not None

    @pytest.mark.asyncio
    async def test_submit_complaint_invalid_phone(self, service, mock_repo):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GrievanceCreate(
                reporter_name="John",
                reporter_phone="grievance",
                complaint_type="service",
                details="Bad experience",
            )

    @pytest.mark.asyncio
    async def test_update_ticket(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        mock_repo.get_ticket.return_value = ticket
        payload = GrievanceUpdate(resolution_notes="Investigated")
        result = await service.update_ticket(ticket_id, payload, actor_id=uuid.uuid4())
        assert result.resolution_notes == "Investigated"

    @pytest.mark.asyncio
    async def test_update_ticket_not_found(self, service, mock_repo):
        mock_repo.get_ticket.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_ticket(uuid.uuid4(), GrievanceUpdate())

    @pytest.mark.asyncio
    async def test_update_ticket_invalid_transition(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.CLOSED,
        )
        mock_repo.get_ticket.return_value = ticket
        payload = GrievanceUpdate(status=GrievanceStatus.OPEN)
        with pytest.raises(ValidationFailedError, match="Cannot transition"):
            await service.update_ticket(ticket_id, payload)

    @pytest.mark.asyncio
    async def test_update_ticket_status(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        mock_repo.get_ticket.return_value = ticket
        result = await service.update_ticket_status(
            ticket_id,
            GrievanceStatus.INVESTIGATING,
            actor_id=uuid.uuid4(),
        )
        assert result.status == GrievanceStatus.INVESTIGATING

    @pytest.mark.asyncio
    async def test_update_ticket_status_invalid(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.CLOSED,
        )
        mock_repo.get_ticket.return_value = ticket
        with pytest.raises(ValidationFailedError, match="Cannot transition"):
            await service.update_ticket_status(ticket_id, GrievanceStatus.OPEN)

    @pytest.mark.asyncio
    async def test_assign_ticket(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        mock_repo.get_ticket.return_value = ticket
        result = await service.assign_ticket(ticket_id, admin_id, actor_id=uuid.uuid4())
        assert result.assigned_to_admin_id == admin_id

    @pytest.mark.asyncio
    async def test_assign_ticket_not_found(self, service, mock_repo):
        mock_repo.get_ticket.return_value = None
        with pytest.raises(NotFoundError):
            await service.assign_ticket(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_ticket(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        mock_repo.get_ticket.return_value = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        result = await service.get_ticket(ticket_id)
        assert result.id == ticket_id

    @pytest.mark.asyncio
    async def test_get_ticket_not_found(self, service, mock_repo):
        mock_repo.get_ticket.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_ticket(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_tickets(self, service, mock_repo):
        ticket = GrievanceTicket(
            id=uuid.uuid4(),
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        mock_repo.count_tickets.return_value = 1
        mock_repo.list_tickets.return_value = [ticket]
        tickets, meta = await service.list_tickets()
        assert len(tickets) == 1
        assert meta.total == 1

    @pytest.mark.asyncio
    async def test_list_tickets_with_filter(self, service, mock_repo):
        ticket = GrievanceTicket(
            id=uuid.uuid4(),
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        mock_repo.count_tickets.return_value = 1
        mock_repo.list_tickets.return_value = [ticket]
        filt = GrievanceListFilter(status=GrievanceStatus.OPEN)
        tickets, meta = await service.list_tickets(filter_params=filt)
        assert len(tickets) == 1

    @pytest.mark.asyncio
    async def test_add_comment(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        mock_repo.get_ticket.return_value = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        comment_id = uuid.uuid4()
        mock_repo.create_comment.return_value = GrievanceComment(
            id=comment_id,
            ticket_id=ticket_id,
            author_id=uuid.uuid4(),
            body="Thanks",
            is_internal=False,
        )
        payload = CommentCreate(body="Thanks")
        result = await service.add_comment(ticket_id, payload, author_id=uuid.uuid4())
        assert result.body == "Thanks"

    @pytest.mark.asyncio
    async def test_add_comment_sets_first_responded_at(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        mock_repo.get_ticket.return_value = ticket
        mock_repo.create_comment.return_value = GrievanceComment(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            author_id=uuid.uuid4(),
            body="On it",
            is_internal=True,
        )
        assert ticket.first_responded_at is None
        await service.add_comment(
            ticket_id, CommentCreate(body="On it", is_internal=True), author_id=uuid.uuid4()
        )
        assert ticket.first_responded_at is not None

    @pytest.mark.asyncio
    async def test_escalate_ticket(self, service, mock_repo, mock_audit):
        ticket_id = uuid.uuid4()
        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.INVESTIGATING,
            escalation_level=0,
        )
        mock_repo.get_ticket.return_value = ticket
        admin_id = uuid.uuid4()
        result = await service.escalate_ticket(
            ticket_id,
            GrievanceEscalate(escalated_to_admin_id=admin_id, reason="SLA breach"),
            actor_id=uuid.uuid4(),
        )
        assert result.escalation_level == 1
        assert result.escalated_to_admin_id == admin_id
        assert result.escalated_at is not None

    @pytest.mark.asyncio
    async def test_escalate_closed_ticket_rejected(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        mock_repo.get_ticket.return_value = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.CLOSED,
        )
        with pytest.raises(ValidationFailedError, match="closed ticket"):
            await service.escalate_ticket(
                ticket_id, GrievanceEscalate(escalated_to_admin_id=uuid.uuid4())
            )

    @pytest.mark.asyncio
    async def test_add_comment_ticket_not_found(self, service, mock_repo):
        mock_repo.get_ticket.return_value = None
        with pytest.raises(NotFoundError):
            await service.add_comment(uuid.uuid4(), CommentCreate(body="Hi"))

    @pytest.mark.asyncio
    async def test_list_comments(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        mock_repo.get_ticket.return_value = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        mock_repo.list_comments.return_value = [
            GrievanceComment(
                id=uuid.uuid4(),
                ticket_id=ticket_id,
                body="Comment",
            )
        ]
        result = await service.list_comments(ticket_id)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_submit_feedback(self, service, mock_repo):
        fb_id = uuid.uuid4()
        mock_repo.create_feedback.return_value = ServiceFeedback(
            id=fb_id,
            rating=5,
            comments="Great!",
        )
        payload = ServiceFeedbackCreate(rating=5)
        result = await service.submit_feedback(payload)
        assert result.rating == 5

    @pytest.mark.asyncio
    async def test_list_feedback(self, service, mock_repo):
        fb = ServiceFeedback(id=uuid.uuid4(), rating=4)
        mock_repo.count_feedback.return_value = 1
        mock_repo.list_feedback.return_value = [fb]
        results, meta = await service.list_feedback()
        assert len(results) == 1
        assert meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_ticket(self, service, mock_repo):
        ticket_id = uuid.uuid4()
        mock_repo.get_ticket.return_value = GrievanceTicket(
            id=ticket_id,
            reporter_name="J",
            reporter_phone="+1",
            complaint_type="service",
            details="Bad",
            status=GrievanceStatus.OPEN,
        )
        mock_repo.soft_delete_ticket.return_value = None
        await service.soft_delete_ticket(ticket_id)
        mock_repo.soft_delete_ticket.assert_called_once_with(ticket_id)

    @pytest.mark.asyncio
    async def test_soft_delete_ticket_not_found(self, service, mock_repo):
        mock_repo.get_ticket.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_ticket(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_soft_delete_feedback(self, service, mock_repo):
        fb_id = uuid.uuid4()
        mock_repo.get_feedback.return_value = ServiceFeedback(id=fb_id, rating=3)
        mock_repo.soft_delete_feedback.return_value = None
        await service.soft_delete_feedback(fb_id)
        mock_repo.soft_delete_feedback.assert_called_once_with(fb_id)

    @pytest.mark.asyncio
    async def test_soft_delete_feedback_not_found(self, service, mock_repo):
        mock_repo.get_feedback.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_feedback(uuid.uuid4())
