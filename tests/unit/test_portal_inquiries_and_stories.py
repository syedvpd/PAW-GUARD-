"""Unit tests for Contact Inquiry Management and Adopter Success Story Submissions."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams
from pawguard.modules.portal.models import (
    ContactInquiryStatus,
    ContactMessage,
    ContentStatus,
    SuccessStory,
)
from pawguard.modules.portal.repository import PortalRepository
from pawguard.modules.portal.schemas import (
    ContactInquiryRespondRequest,
    ContactMessageCreate,
    SuccessStoryRejectRequest,
    SuccessStoryUpdate,
    SuccessStoryUserSubmit,
)
from pawguard.modules.portal.service import PortalService


class TestContactInquiryManagement:
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
    def service(self, mock_repo, mock_session, mock_audit, mock_arq):
        return PortalService(
            repository=mock_repo,
            session=mock_session,
            audit_service=mock_audit,
            arq_pool=mock_arq,
        )

    @pytest.mark.asyncio
    async def test_public_contact_submission_anonymous(self, service, mock_repo, mock_session):
        """Public unauthenticated user submits inquiry; row is persisted and notification dispatched."""
        mock_repo.get_active_user_by_email.return_value = None

        created_msg = ContactMessage(
            id=uuid.uuid4(),
            name="Jane Doe",
            email="jane@example.com",
            phone="1234567890",
            category="General",
            subject="Question regarding adoption process",
            message="Hello, I want to know the timings for shelter visit.",
            has_consent=True,
            status=ContactInquiryStatus.NEW,
        )
        mock_repo.create_contact_message.return_value = created_msg

        payload = ContactMessageCreate(
            name="Jane Doe",
            email="jane@example.com",
            phone="1234567890",
            category="General",
            subject="Question regarding adoption process",
            message="Hello, I want to know the timings for shelter visit.",
            has_consent=True,
        )

        res = await service.submit_contact_message(payload, user_id=None, ip_address="127.0.0.1")
        assert res is True
        mock_repo.create_contact_message.assert_called_once()
        saved_arg = mock_repo.create_contact_message.call_args[0][0]
        assert saved_arg.name == "Jane Doe"
        assert saved_arg.email == "jane@example.com"
        assert saved_arg.status == ContactInquiryStatus.NEW
        assert saved_arg.user_id is None

    @pytest.mark.asyncio
    async def test_public_contact_submission_authenticated(
        self, service, mock_repo, mock_session, mock_audit
    ):
        """Authenticated user submits contact message; user_id is automatically associated."""
        user_uuid = uuid.uuid4()
        created_msg = ContactMessage(
            id=uuid.uuid4(),
            user_id=user_uuid,
            name="John Smith",
            email="john@example.com",
            subject="Volunteer inquiry",
            message="I'd love to help on weekends.",
            status=ContactInquiryStatus.NEW,
        )
        mock_repo.create_contact_message.return_value = created_msg

        payload = ContactMessageCreate(
            name="John Smith",
            email="john@example.com",
            subject="Volunteer inquiry",
            message="I'd love to help on weekends.",
        )

        res = await service.submit_contact_message(
            payload, user_id=user_uuid, ip_address="192.168.1.1"
        )
        assert res is True
        saved_arg = mock_repo.create_contact_message.call_args[0][0]
        assert saved_arg.user_id == user_uuid
        assert saved_arg.email == "john@example.com"
        mock_audit.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_admin_list_contact_inquiries_paginated(self, service, mock_repo):
        """Admin lists inquiries with filters."""
        inquiry_1 = ContactMessage(
            id=uuid.uuid4(),
            name="Alice",
            email="alice@example.com",
            subject="Help",
            message="Need help",
            status=ContactInquiryStatus.NEW,
        )
        mock_repo.list_contact_inquiries_paginated.return_value = ([inquiry_1], 1)

        page = PageParams(page=1, page_size=10)
        items, meta = await service.list_contact_inquiries_paginated(
            page_params=page,
            status=ContactInquiryStatus.NEW,
            category="Rescue",
        )
        assert len(items) == 1
        assert meta.total == 1
        assert items[0].name == "Alice"

    @pytest.mark.asyncio
    async def test_admin_get_contact_inquiry_detail(self, service, mock_repo):
        """Admin views detail of an inquiry."""
        inq_id = uuid.uuid4()
        inquiry = ContactMessage(
            id=inq_id,
            name="Bob",
            email="bob@example.com",
            subject="Donation receipt",
            message="Where is my receipt?",
            status=ContactInquiryStatus.NEW,
        )
        mock_repo.get_contact_inquiry.return_value = inquiry

        res = await service.get_contact_inquiry(inq_id)
        assert res.id == inq_id
        assert res.email == "bob@example.com"

    @pytest.mark.asyncio
    async def test_admin_get_contact_inquiry_not_found(self, service, mock_repo):
        """NotFoundError raised when inquiry does not exist."""
        inq_id = uuid.uuid4()
        mock_repo.get_contact_inquiry.return_value = None

        with pytest.raises(NotFoundError):
            await service.get_contact_inquiry(inq_id)

    @pytest.mark.asyncio
    async def test_contact_inquiry_status_transition_valid(
        self, service, mock_repo, mock_session, mock_audit
    ):
        """Valid state machine transitions work correctly and log audit."""
        inq_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        inquiry = ContactMessage(
            id=inq_id,
            status=ContactInquiryStatus.NEW,
        )
        mock_repo.get_contact_inquiry.return_value = inquiry

        res = await service.update_inquiry_status(
            inquiry_id=inq_id,
            new_status=ContactInquiryStatus.IN_PROGRESS,
            actor_id=admin_id,
        )
        assert res.status == ContactInquiryStatus.IN_PROGRESS
        mock_audit.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_contact_inquiry_status_transition_invalid(self, service, mock_repo):
        """Invalid state machine transition raises ValidationFailedError."""
        inq_id = uuid.uuid4()
        inquiry = ContactMessage(
            id=inq_id,
            status=ContactInquiryStatus.CLOSED,
        )
        mock_repo.get_contact_inquiry.return_value = inquiry

        with pytest.raises(ValidationFailedError, match="Cannot transition inquiry from"):
            await service.update_inquiry_status(
                inquiry_id=inq_id,
                new_status=ContactInquiryStatus.NEW,
            )

    @pytest.mark.asyncio
    async def test_contact_inquiry_assignment(self, service, mock_repo, mock_session, mock_audit):
        """Assigning inquiry to staff updates assigned_to_user_id and status to in_progress if new."""
        inq_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        inquiry = ContactMessage(
            id=inq_id,
            status=ContactInquiryStatus.NEW,
            assigned_to_user_id=None,
        )
        mock_repo.get_contact_inquiry.return_value = inquiry

        # Mock user lookup for staff
        mock_staff_user = MagicMock(id=staff_id, is_active=True)
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = mock_staff_user
        mock_session.execute.return_value = mock_res

        res = await service.assign_inquiry(
            inquiry_id=inq_id,
            assigned_to_user_id=staff_id,
            actor_id=admin_id,
        )
        assert res.assigned_to_user_id == staff_id
        assert res.status == ContactInquiryStatus.IN_PROGRESS
        mock_audit.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_contact_inquiry_respond(self, service, mock_repo, mock_session, mock_audit):
        """Staff response sets response, responder, timestamps, and optional notes."""
        inq_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        inquiry = ContactMessage(
            id=inq_id,
            email="visitor@example.com",
            subject="Question",
            status=ContactInquiryStatus.IN_PROGRESS,
        )
        mock_repo.get_contact_inquiry.return_value = inquiry

        payload = ContactInquiryRespondRequest(
            staff_response="Thank you for reaching out. We are open from 9 AM to 6 PM.",
            internal_notes="Responded with visiting hours.",
            new_status=ContactInquiryStatus.RESOLVED,
        )

        res = await service.respond_to_inquiry(
            inquiry_id=inq_id,
            payload=payload,
            actor_id=staff_id,
        )
        assert res.staff_response == "Thank you for reaching out. We are open from 9 AM to 6 PM."
        assert "Responded with visiting hours." in (res.internal_notes or "")
        assert res.responded_by_user_id == staff_id
        assert res.responded_at is not None
        assert res.status == ContactInquiryStatus.RESOLVED
        mock_audit.record.assert_called_once()


class TestAdopterSuccessStorySubmission:
    @pytest.fixture
    def mock_repo(self):
        return AsyncMock(spec=PortalRepository)

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
    def service(self, mock_repo, mock_session, mock_audit):
        return PortalService(
            repository=mock_repo,
            session=mock_session,
            audit_service=mock_audit,
        )

    @pytest.mark.asyncio
    async def test_submit_user_story_success(self, service, mock_repo, mock_session, mock_audit):
        """Authenticated adopter submits story with consent; status is pending_review."""
        adopter_id = uuid.uuid4()

        mock_repo.get_story_by_slug.return_value = None
        mock_repo.create_story.side_effect = lambda story: story

        payload = SuccessStoryUserSubmit(
            title="Max Found His Forever Home",
            summary="Max is loving his new yard.",
            body="From the moment we brought Max home, he became part of our family.",
            hero_image_url="https://assets.pawguard.org/stories/max.jpg",
            has_consent=True,
        )

        res = await service.submit_user_story(
            user_id=adopter_id,
            payload=payload,
            actor_id=adopter_id,
        )
        assert res.title == "Max Found His Forever Home"
        assert res.adopter_id == adopter_id
        assert res.has_consent is True
        assert res.status == ContentStatus.PENDING_REVIEW
        mock_audit.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_user_story_missing_consent(self, service):
        """Submission without explicit consent is rejected."""
        adopter_id = uuid.uuid4()
        payload = SuccessStoryUserSubmit(
            title="Bella's Story",
            summary="Bella is doing great.",
            body="We adopted Bella last month.",
            has_consent=False,
        )

        with pytest.raises(ValidationFailedError, match="Consent to publish"):
            await service.submit_user_story(
                user_id=adopter_id,
                payload=payload,
            )

    @pytest.mark.asyncio
    async def test_submit_user_story_with_valid_dog_association(
        self, service, mock_repo, mock_session
    ):
        """Submission with dog_id verifies dog exists and user is associated."""
        adopter_id = uuid.uuid4()
        dog_id = uuid.uuid4()

        # Mock dog lookup
        mock_dog = MagicMock(id=dog_id)
        # Mock adoption lookup
        mock_adoption = MagicMock(id=uuid.uuid4(), dog_id=dog_id, adopter_id=adopter_id)

        dog_exec_res = MagicMock()
        dog_exec_res.scalar_one_or_none.return_value = mock_dog

        adopt_exec_res = MagicMock()
        adopt_exec_res.scalars.return_value.first.return_value = mock_adoption

        mock_session.execute.side_effect = [dog_exec_res, adopt_exec_res]
        mock_repo.get_story_by_slug.return_value = None
        mock_repo.create_story.side_effect = lambda story: story

        payload = SuccessStoryUserSubmit(
            title="Rocky's Journey",
            summary="Rocky loves playing fetch.",
            body="Rocky was adopted three weeks ago and is thriving.",
            dog_id=dog_id,
            has_consent=True,
        )

        res = await service.submit_user_story(
            user_id=adopter_id,
            payload=payload,
        )
        assert res.dog_id == dog_id
        assert res.status == ContentStatus.PENDING_REVIEW

    @pytest.mark.asyncio
    async def test_submit_user_story_with_unassociated_dog(self, service, mock_session):
        """Submission with dog_id that caller does not own/associate with is rejected."""
        adopter_id = uuid.uuid4()
        dog_id = uuid.uuid4()

        mock_dog = MagicMock(id=dog_id)
        dog_exec_res = MagicMock()
        dog_exec_res.scalar_one_or_none.return_value = mock_dog

        adopt_exec_res = MagicMock()
        adopt_exec_res.scalars.return_value.first.return_value = None  # No adoption application

        mock_session.execute.side_effect = [dog_exec_res, adopt_exec_res]

        payload = SuccessStoryUserSubmit(
            title="Stolen Dog Story",
            summary="Trying to claim someone else's dog.",
            body="Fake story.",
            dog_id=dog_id,
            has_consent=True,
        )

        with pytest.raises(ValidationFailedError, match="only submit a success story for a dog"):
            await service.submit_user_story(
                user_id=adopter_id,
                payload=payload,
            )

    @pytest.mark.asyncio
    async def test_admin_publish_story_enforces_consent(self, service, mock_repo):
        """Admin publishing a story without consent fails validation."""
        story_id = uuid.uuid4()
        story = SuccessStory(
            id=story_id,
            title="Consent Withdrawn Story",
            summary="Summary",
            body="Body",
            status=ContentStatus.PENDING_REVIEW,
            has_consent=False,
        )
        mock_repo.get_story.return_value = story

        with pytest.raises(ValidationFailedError, match="without adopter consent"):
            await service.update_story(
                story_id=story_id,
                payload=SuccessStoryUpdate(status=ContentStatus.PUBLISHED),
            )

    @pytest.mark.asyncio
    async def test_admin_reject_story_with_reason(
        self, service, mock_repo, mock_session, mock_audit
    ):
        """Admin can reject a submission with a rejection reason."""
        story_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        story = SuccessStory(
            id=story_id,
            title="Inappropriate Story",
            summary="Summary",
            body="Body",
            status=ContentStatus.PENDING_REVIEW,
        )
        mock_repo.get_story.return_value = story

        payload = SuccessStoryRejectRequest(
            rejection_reason="Photo quality is too blurry. Please resubmit with a clearer picture."
        )

        res = await service.reject_story(
            story_id=story_id,
            payload=payload,
            actor_id=admin_id,
        )
        assert res.status == ContentStatus.REJECTED
        assert (
            res.rejection_reason
            == "Photo quality is too blurry. Please resubmit with a clearer picture."
        )
        mock_audit.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_user_stories_me(self, service, mock_repo):
        """User can list their own submitted stories."""
        adopter_id = uuid.uuid4()
        story = SuccessStory(
            id=uuid.uuid4(),
            adopter_id=adopter_id,
            title="My Pet Story",
            summary="Sum",
            body="Body",
            status=ContentStatus.PENDING_REVIEW,
        )
        mock_repo.list_user_stories_paginated.return_value = ([story], 1)

        items, meta = await service.list_user_stories_paginated(
            user_id=adopter_id,
            page_params=PageParams(page=1, page_size=10),
        )
        assert len(items) == 1
        assert meta.total == 1
        assert items[0].adopter_id == adopter_id
