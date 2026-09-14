"""Unit tests for Contact Inquiries and Grievance Ticket User Ownership, SLA, RBAC & Dashboard Flows."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.modules.grievance.models import (
    GrievanceComment,
    GrievanceStatus,
    GrievanceTicket,
)
from pawguard.modules.grievance.repository import GrievanceRepository
from pawguard.modules.grievance.schemas import (
    GrievanceCreate,
    GrievanceEscalate,
    GrievanceListFilter,
    GrievanceUpdate,
)
from pawguard.modules.grievance.service import GrievanceService
from pawguard.modules.portal.models import (
    ContactInquiryStatus,
    ContactMessage,
)
from pawguard.modules.portal.repository import PortalRepository
from pawguard.modules.portal.schemas import (
    ContactInquiryRespondRequest,
    ContactMessageCreate,
    UserContactInquiryResponse,
    UserDashboardSummary,
)
from pawguard.modules.portal.service import PortalService
from pawguard.services.audit_service import AuditService


class TestUserContactInquiryFlow:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=PortalRepository)
        repo.get_active_user_by_email = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def mock_audit(self):
        audit = AsyncMock()
        audit.record = AsyncMock()
        return audit

    @pytest.fixture
    def mock_arq(self):
        arq = AsyncMock()
        arq.enqueue_job = AsyncMock()
        return arq

    @pytest.fixture
    def portal_service(self, mock_repo, mock_session, mock_audit, mock_arq):
        return PortalService(
            repository=mock_repo,
            session=mock_session,
            audit_service=mock_audit,
            arq_pool=mock_arq,
        )

    @pytest.mark.asyncio
    async def test_authenticated_contact_submission(self, portal_service, mock_repo):
        """1. Authenticated user submits inquiry -> stored with user_id and email."""
        user_id = uuid.uuid4()
        user_email = "citizen@example.com"

        created_msg = ContactMessage(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Citizen One",
            email=user_email,
            phone="+91-9876543210",
            category="adoption",
            subject="Adoption Procedure Question",
            message="How do I schedule a meet and greet?",
            status=ContactInquiryStatus.NEW,
            has_consent=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_repo.create_contact_message.return_value = created_msg

        payload = ContactMessageCreate(
            name="Citizen One",
            email=user_email,
            phone="+91-9876543210",
            category="adoption",
            subject="Adoption Procedure Question",
            message="How do I schedule a meet and greet?",
            has_consent=True,
        )

        ok = await portal_service.submit_contact_message(
            payload,
            user_id=user_id,
            ip_address="192.168.1.1",
        )
        assert ok is True
        mock_repo.create_contact_message.assert_called_once()
        persisted = mock_repo.create_contact_message.call_args[0][0]
        assert persisted.user_id == user_id
        assert persisted.email == user_email.lower()
        assert persisted.status == ContactInquiryStatus.NEW

    @pytest.mark.asyncio
    async def test_user_retrieves_own_contact_inquiries(self, portal_service, mock_repo):
        """2. Submitting user lists only their own contact inquiries."""
        user_id = uuid.uuid4()
        user_email = "citizen@example.com"
        inquiry_1 = ContactMessage(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Citizen One",
            email=user_email,
            category="general",
            subject="Query 1",
            message="Message 1",
            status=ContactInquiryStatus.NEW,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_repo.list_contact_inquiries_paginated.return_value = ([inquiry_1], 1)

        inquiries, meta = await portal_service.list_user_contact_inquiries(
            user_id=user_id,
            user_email=user_email,
            page_params=PageParams(page=1, page_size=10),
        )

        assert len(inquiries) == 1
        assert inquiries[0].id == inquiry_1.id
        assert meta.total == 1
        mock_repo.list_contact_inquiries_paginated.assert_called_once_with(
            PageParams(page=1, page_size=10),
            user_id=user_id,
            user_email=user_email,
            status=None,
            category=None,
            search=None,
            sort=None,
        )

    @pytest.mark.asyncio
    async def test_user_contact_inquiry_idor_protection(self, portal_service, mock_repo):
        """3. Unauthorized user attempting to access another user's inquiry gets 404."""
        inquiry_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        other_email = "other@example.com"

        # Repo returns None because user_id/email filter does not match
        mock_repo.get_user_contact_inquiry.return_value = None

        with pytest.raises(NotFoundError, match="Contact inquiry not found"):
            await portal_service.get_user_contact_inquiry(
                inquiry_id=inquiry_id,
                user_id=other_user_id,
                user_email=other_email,
            )

    @pytest.mark.asyncio
    async def test_user_response_schema_excludes_internal_notes(self):
        """4. User-facing schema does not leak internal notes or staff assignees."""
        inquiry = ContactMessage(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="Jane Doe",
            email="jane@example.com",
            phone="+91-1111111111",
            category="medical",
            subject="Vaccination Inquiry",
            message="Are rabies shots available?",
            status=ContactInquiryStatus.RESOLVED,
            assigned_to_user_id=uuid.uuid4(),
            staff_response="Yes, rabies shots are available daily from 9am to 5pm.",
            internal_notes="CONFIDENTIAL: Verified clinic stock with Dr. Sharma.",
            responded_at=datetime.now(UTC),
            responded_by_user_id=uuid.uuid4(),
            has_consent=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        user_dto = UserContactInquiryResponse.model_validate(inquiry)
        dto_dict = user_dto.model_dump()

        assert (
            dto_dict["staff_response"] == "Yes, rabies shots are available daily from 9am to 5pm."
        )
        assert "internal_notes" not in dto_dict
        assert "assigned_to_user_id" not in dto_dict
        assert "responded_by_user_id" not in dto_dict

    @pytest.mark.asyncio
    async def test_admin_contact_inquiry_lifecycle(self, portal_service, mock_repo):
        """5. Admin can assign, respond, and update status of inquiries."""
        inquiry_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        inquiry = ContactMessage(
            id=inquiry_id,
            name="Jane",
            email="jane@example.com",
            subject="Help",
            message="Need help",
            status=ContactInquiryStatus.NEW,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_repo.get_contact_inquiry.return_value = inquiry

        # Assign
        assigned = await portal_service.assign_inquiry(
            inquiry_id=inquiry_id,
            assigned_to_user_id=staff_id,
            actor_id=admin_id,
        )
        assert assigned.assigned_to_user_id == staff_id
        assert assigned.status == ContactInquiryStatus.IN_PROGRESS

        # Respond & resolve
        mock_repo.get_contact_inquiry.return_value = assigned
        responded = await portal_service.respond_to_inquiry(
            inquiry_id=inquiry_id,
            payload=ContactInquiryRespondRequest(
                staff_response="We have reviewed your request.",
                internal_notes="Staff handled promptly.",
                new_status=ContactInquiryStatus.RESOLVED,
            ),
            actor_id=admin_id,
        )
        assert responded.staff_response == "We have reviewed your request."
        assert "Staff handled promptly." in (responded.internal_notes or "")
        assert responded.status == ContactInquiryStatus.RESOLVED


class TestUserGrievanceFlow:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=GrievanceRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def grievance_service(self, mock_repo, mock_audit):
        return GrievanceService(mock_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_grievance_submission_creates_sla_due_date(self, grievance_service, mock_repo):
        """6. Grievance submission enforces mandatory 72h SLA due date."""
        user_email = "citizen@example.com"

        mock_repo.create_ticket.side_effect = lambda t: t

        payload = GrievanceCreate(
            reporter_name="Citizen One",
            reporter_phone="+91-9876543210",
            reporter_email=user_email,
            complaint_type="Rescue Response Delay",
            details="Ambulance arrived 4 hours late for injured animal.",
        )

        now_before = datetime.now(UTC)
        ticket = await grievance_service.submit_complaint(payload)
        now_after = datetime.now(UTC)

        assert ticket.reporter_name == "Citizen One"
        assert ticket.reporter_email == user_email
        assert ticket.status == GrievanceStatus.OPEN
        assert ticket.sla_due_at is not None
        # SLA must be approximately 72 hours from creation
        expected_sla_min = now_before + timedelta(hours=71, minutes=59)
        expected_sla_max = now_after + timedelta(hours=72, minutes=1)
        assert expected_sla_min <= ticket.sla_due_at <= expected_sla_max

    @pytest.mark.asyncio
    async def test_user_lists_own_grievances(self, grievance_service, mock_repo):
        """7. Submitting user can list only their own grievance tickets."""
        user_email = "citizen@example.com"
        ticket = GrievanceTicket(
            id=uuid.uuid4(),
            reporter_name="Citizen One",
            reporter_phone="+91-9876543210",
            reporter_email=user_email,
            complaint_type="Rescue Delay",
            details="Delay observed",
            status=GrievanceStatus.OPEN,
            sla_due_at=datetime.now(UTC) + timedelta(hours=72),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_repo.count_tickets.return_value = 1
        mock_repo.list_tickets.return_value = [ticket]

        tickets, meta = await grievance_service.list_my_tickets(
            user_email=user_email,
            page_params=PageParams(page=1, page_size=10),
            filter_params=GrievanceListFilter(status=GrievanceStatus.OPEN),
        )

        assert len(tickets) == 1
        assert tickets[0].reporter_email == user_email
        assert meta.total == 1
        mock_repo.list_tickets.assert_called_once_with(
            reporter_email=user_email,
            page_params=PageParams(page=1, page_size=10),
            status=GrievanceStatus.OPEN,
            complaint_type=None,
            search=None,
        )

    @pytest.mark.asyncio
    async def test_user_grievance_idor_protection(self, grievance_service, mock_repo):
        """8. Submitting user cannot access another user's grievance ticket."""
        ticket_id = uuid.uuid4()
        attacker_email = "attacker@example.com"

        mock_repo.get_user_ticket.return_value = None

        with pytest.raises(NotFoundError, match="Grievance ticket not found"):
            await grievance_service.get_my_ticket(ticket_id, user_email=attacker_email)

    @pytest.mark.asyncio
    async def test_user_comments_excludes_internal_notes(self, grievance_service, mock_repo):
        """9. User viewing comments sees only public comments (is_internal=False)."""
        ticket_id = uuid.uuid4()
        user_email = "citizen@example.com"

        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="Citizen One",
            reporter_phone="+91-9876543210",
            reporter_email=user_email,
            complaint_type="Delay",
            details="Details",
            status=GrievanceStatus.INVESTIGATING,
        )
        mock_repo.get_user_ticket.return_value = ticket

        public_comment = GrievanceComment(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            author_id=uuid.uuid4(),
            body="We have dispatched a team to inspect the location.",
            is_internal=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_repo.list_comments.return_value = [public_comment]

        comments = await grievance_service.list_my_ticket_comments(ticket_id, user_email=user_email)
        assert len(comments) == 1
        assert comments[0].body == "We have dispatched a team to inspect the location."
        assert comments[0].is_internal is False
        mock_repo.list_comments.assert_called_once_with(ticket_id, public_only=True)

    @pytest.mark.asyncio
    async def test_grievance_admin_resolution_and_escalation(self, grievance_service, mock_repo):
        """10. Admin can assign, resolve, and escalate grievance tickets."""
        ticket_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        senior_admin_id = uuid.uuid4()

        ticket = GrievanceTicket(
            id=ticket_id,
            reporter_name="Citizen",
            reporter_phone="+91-1",
            complaint_type="Staff Conduct",
            details="Rude behavior",
            status=GrievanceStatus.OPEN,
            escalation_level=0,
        )
        mock_repo.get_ticket.return_value = ticket

        # Assign
        assigned = await grievance_service.assign_ticket(
            ticket_id=ticket_id,
            admin_id=admin_id,
            actor_id=admin_id,
        )
        assert assigned.assigned_to_admin_id == admin_id

        # Escalate
        escalated = await grievance_service.escalate_ticket(
            ticket_id=ticket_id,
            payload=GrievanceEscalate(
                escalated_to_admin_id=senior_admin_id,
                reason="SLA response window approaching deadline",
            ),
            actor_id=admin_id,
        )
        assert escalated.escalation_level == 1
        assert escalated.escalated_to_admin_id == senior_admin_id

        # Resolve
        resolved = await grievance_service.update_ticket(
            ticket_id=ticket_id,
            payload=GrievanceUpdate(
                status=GrievanceStatus.INVESTIGATING,
            ),
            actor_id=admin_id,
        )
        assert resolved.status == GrievanceStatus.INVESTIGATING

        mock_repo.get_ticket.return_value = resolved
        final_resolved = await grievance_service.update_ticket(
            ticket_id=ticket_id,
            payload=GrievanceUpdate(
                status=GrievanceStatus.RESOLVED,
                resolution_notes="Staff member counselled and warning issued.",
            ),
            actor_id=admin_id,
        )
        assert final_resolved.status == GrievanceStatus.RESOLVED
        assert final_resolved.resolution_notes == "Staff member counselled and warning issued."


class TestUserDashboardSummaryIntegration:
    @pytest.mark.asyncio
    async def test_dashboard_summary_includes_inquiries_and_grievances(self):
        """11. UserDashboardSummary includes contact_inquiries and grievance_tickets."""
        dashboard = UserDashboardSummary(
            rescue_cases=[],
            adoption_applications=[],
            volunteer_profile=None,
            volunteer_status="NOT_APPLIED",
            volunteer_application=None,
            foster_profile=None,
            donations=[],
            lost_found_reports=[],
            contact_inquiries=[
                {
                    "id": str(uuid.uuid4()),
                    "category": "general",
                    "subject": "Visiting Hours",
                    "message": "What are your hours?",
                    "status": "new",
                    "staff_response": None,
                    "responded_at": None,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ],
            grievance_tickets=[
                {
                    "id": str(uuid.uuid4()),
                    "complaint_type": "Rescue Delay",
                    "details": "Delayed response",
                    "status": "open",
                    "resolution_notes": None,
                    "sla_due_at": (datetime.now(UTC) + timedelta(hours=72)).isoformat(),
                    "first_responded_at": None,
                    "escalation_level": 0,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ],
        )

        data = dashboard.model_dump()
        assert len(data["contact_inquiries"]) == 1
        assert data["contact_inquiries"][0]["subject"] == "Visiting Hours"
        assert len(data["grievance_tickets"]) == 1
        assert data["grievance_tickets"][0]["complaint_type"] == "Rescue Delay"
        assert data["grievance_tickets"][0]["sla_due_at"] is not None
