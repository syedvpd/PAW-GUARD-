"""Unit tests for VolunteerService with mocked repository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from pawguard.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from pawguard.modules.auth.models import User
from pawguard.modules.volunteer.models import (
    ApplicationStatus,
    AttendanceStatus,
    ShiftAttendance,
    VolunteerApplication,
    VolunteerProfile,
    VolunteerShift,
    VolunteerStatus,
)
from pawguard.modules.volunteer.repository import VolunteerRepository
from pawguard.modules.volunteer.schemas import (
    VolunteerAdminIntakeRequest,
    VolunteerProfileCreate,
    VolunteerProfileUpdate,
    VolunteerShiftCreate,
)
from pawguard.modules.volunteer.service import VolunteerService
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService


class TestVolunteerService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=VolunteerRepository)
        repo._session = AsyncMock()
        # `session.add` is synchronous; keep it a plain Mock so the service's
        # synchronous `.add(stored)` call doesn't leak an un-awaited coroutine.
        repo._session.add = Mock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return VolunteerService(mock_repo)

    @pytest.mark.asyncio
    async def test_apply_to_volunteer(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_application_by_user_id.return_value = None
        mock_repo.get_profile_by_user_id.return_value = None
        application_id = uuid.uuid4()
        mock_repo.create_application.return_value = None
        mock_repo.get_application_by_id.return_value = VolunteerApplication(
            id=application_id,
            user_id=user_id,
            status=ApplicationStatus.SUBMITTED,
            emergency_contact_name="Jane",
            emergency_contact_phone="+123",
        )
        payload = VolunteerProfileCreate(
            emergency_contact_name="Jane",
            emergency_contact_phone="+123",
        )
        result = await service.apply_to_volunteer(user_id, payload)
        assert result.status == ApplicationStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_apply_to_volunteer_records_audit(self, mock_repo):
        """Self-service applications are public mutations - they must be
        audited with the actor id and IP (PRR §6.1)."""
        mock_audit = AsyncMock(spec=AuditService)
        svc = VolunteerService(mock_repo, audit_service=mock_audit)
        user_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        mock_repo.get_application_by_user_id.return_value = None
        mock_repo.get_profile_by_user_id.return_value = None
        mock_repo.create_application.return_value = None
        mock_repo.get_application_by_id.return_value = VolunteerApplication(
            id=uuid.uuid4(),
            user_id=user_id,
            status=ApplicationStatus.SUBMITTED,
            emergency_contact_name="Jane",
            emergency_contact_phone="+123",
        )
        payload = VolunteerProfileCreate(
            emergency_contact_name="Jane",
            emergency_contact_phone="+123",
        )
        await svc.apply_to_volunteer(
            user_id,
            payload,
            actor_id=actor_id,
            ip_address="203.0.113.9",
        )
        mock_audit.record.assert_awaited_once()
        kwargs = mock_audit.record.call_args.kwargs
        assert kwargs["event_type"].value == "volunteer_application_submitted"
        assert kwargs["actor_id"] == actor_id
        assert kwargs["ip_address"] == "203.0.113.9"

    @pytest.mark.asyncio
    async def test_apply_to_volunteer_already_exists(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_application_by_user_id.return_value = VolunteerApplication(
            id=uuid.uuid4(),
            user_id=user_id,
            status=ApplicationStatus.SUBMITTED,
            emergency_contact_name="Jane",
            emergency_contact_phone="+123",
        )
        with pytest.raises(ConflictError, match="already applied"):
            await service.apply_to_volunteer(
                user_id,
                VolunteerProfileCreate(
                    emergency_contact_name="Jane",
                    emergency_contact_phone="+123",
                ),
            )

    @pytest.mark.asyncio
    async def test_admin_volunteer_intake_new_applicant(self, mock_repo):
        coordinator_id = uuid.uuid4()
        applicant_user_id = uuid.uuid4()
        app_id = uuid.uuid4()

        mock_audit = AsyncMock(spec=AuditService)
        svc = VolunteerService(mock_repo, audit_service=mock_audit)

        # Mock UserRepository calls inside admin_volunteer_intake
        mock_user = User(
            id=applicant_user_id,
            email="prasad@gmail.com",
            phone="6303001088",
            full_name="Prasad",
        )
        mock_app = VolunteerApplication(
            id=app_id,
            user_id=applicant_user_id,
            status=ApplicationStatus.SUBMITTED,
            emergency_contact_name="Prasad",
            emergency_contact_phone="6303001088",
            applied_role="Shelter Support",
            availability="Weekends & Mornings",
            notes="yeah have some experience with taking care of the pets",
        )

        with (
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_email",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_phone",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_default_role",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.create",
                AsyncMock(return_value=mock_user),
            ),
        ):
            mock_repo.create_application.return_value = None
            mock_repo.get_application_by_id.return_value = mock_app

            payload = VolunteerAdminIntakeRequest(
                full_name="Prasad",
                email="prasad@gmail.com",
                phone="6303001088",
                preferred_role="Shelter Support",
                availability="Weekends & Mornings",
                notes="yeah have some experience with taking care of the pets",
            )

            res = await svc.admin_volunteer_intake(
                payload,
                actor_id=coordinator_id,
                ip_address="127.0.0.1",
            )

            assert res.id == app_id
            assert res.user_id == applicant_user_id
            assert res.user_id != coordinator_id
            mock_audit.record.assert_awaited_once()
            audit_kwargs = mock_audit.record.call_args.kwargs
            assert audit_kwargs["actor_id"] == coordinator_id
            assert audit_kwargs["metadata"]["user_id"] == str(applicant_user_id)

    @pytest.mark.asyncio
    async def test_admin_volunteer_intake_second_new_applicant(self, mock_repo):
        coordinator_id = uuid.uuid4()
        bruce_id = uuid.uuid4()

        svc = VolunteerService(mock_repo)
        mock_user = User(
            id=bruce_id,
            email="unique-bruce@example.com",
            phone="unique phone",
            full_name="Bruce",
        )
        mock_app = VolunteerApplication(
            id=uuid.uuid4(),
            user_id=bruce_id,
            status=ApplicationStatus.SUBMITTED,
            emergency_contact_name="Bruce",
            emergency_contact_phone="unique phone",
        )

        with (
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_email",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_phone",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_default_role",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.create",
                AsyncMock(return_value=mock_user),
            ),
        ):
            mock_repo.create_application.return_value = None
            mock_repo.get_application_by_id.return_value = mock_app

            payload = VolunteerAdminIntakeRequest(
                full_name="Bruce",
                email="unique-bruce@example.com",
                phone="unique phone",
            )

            res = await svc.admin_volunteer_intake(
                payload,
                actor_id=coordinator_id,
            )
            assert res.user_id == bruce_id
            assert res.user_id != coordinator_id

    @pytest.mark.asyncio
    async def test_admin_volunteer_intake_duplicate_email_with_active_profile(self, mock_repo):
        coordinator_id = uuid.uuid4()
        existing_applicant_id = uuid.uuid4()
        svc = VolunteerService(mock_repo)

        existing_user = User(
            id=existing_applicant_id,
            email="prasad@gmail.com",
            phone="6303001088",
            full_name="Prasad",
        )
        existing_app = VolunteerApplication(
            id=uuid.uuid4(),
            user_id=existing_applicant_id,
            status=ApplicationStatus.APPROVED,
            emergency_contact_name="Prasad",
            emergency_contact_phone="6303001088",
        )
        existing_profile = VolunteerProfile(
            id=uuid.uuid4(),
            user_id=existing_applicant_id,
            status=VolunteerStatus.ACTIVE,
            emergency_contact_name="Prasad",
            emergency_contact_phone="6303001088",
        )

        mock_repo.get_application_by_user_id.return_value = existing_app
        mock_repo.get_profile_by_user_id.return_value = existing_profile

        with (
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_email",
                AsyncMock(return_value=existing_user),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_phone",
                AsyncMock(return_value=None),
            ),
        ):
            payload = VolunteerAdminIntakeRequest(
                full_name="Prasad",
                email="prasad@gmail.com",
                phone="6303001088",
            )
            with pytest.raises(ConflictError, match="already active and approved"):
                await svc.admin_volunteer_intake(payload, actor_id=coordinator_id)

    @pytest.mark.asyncio
    async def test_admin_volunteer_intake_updates_existing_submitted_application(self, mock_repo):
        coordinator_id = uuid.uuid4()
        existing_applicant_id = uuid.uuid4()
        svc = VolunteerService(mock_repo)

        existing_user = User(
            id=existing_applicant_id,
            email="prasad@gmail.com",
            phone="6303001088",
            full_name="Prasad",
        )
        app_id = uuid.uuid4()
        existing_app = VolunteerApplication(
            id=app_id,
            user_id=existing_applicant_id,
            status=ApplicationStatus.SUBMITTED,
            emergency_contact_name="Old Contact",
            emergency_contact_phone="6303001088",
        )

        mock_repo.get_application_by_user_id.return_value = existing_app
        mock_repo.get_application_by_id.return_value = existing_app
        mock_repo.get_profile_by_user_id.return_value = None

        with (
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_email",
                AsyncMock(return_value=existing_user),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_phone",
                AsyncMock(return_value=None),
            ),
        ):
            payload = VolunteerAdminIntakeRequest(
                full_name="Prasad Updated",
                email="prasad@gmail.com",
                phone="6303001088",
                preferred_role="Shelter Support",
                notes="Quick intake note",
            )
            res = await svc.admin_volunteer_intake(payload, actor_id=coordinator_id)
            assert res.id == app_id
            assert res.user_id == existing_applicant_id
            assert res.status == ApplicationStatus.SUBMITTED
            assert res.applied_role == "Shelter Support"
            assert res.notes == "Quick intake note"

    @pytest.mark.asyncio
    async def test_admin_volunteer_intake_coordinator_profile_does_not_prevent_intake(
        self, mock_repo
    ):
        """Regression test: Coordinator having an active volunteer application or profile
        must NOT block intake for new applicants."""
        coordinator_id = uuid.uuid4()
        applicant_id = uuid.uuid4()
        svc = VolunteerService(mock_repo)

        # Coordinator has their own profile/application
        coordinator_app = VolunteerApplication(
            id=uuid.uuid4(),
            user_id=coordinator_id,
            status=ApplicationStatus.APPROVED,
            emergency_contact_name="Coord",
            emergency_contact_phone="999",
        )
        mock_repo.get_application_by_user_id.side_effect = lambda uid: (
            coordinator_app if uid == coordinator_id else None
        )
        mock_repo.get_profile_by_user_id.return_value = None

        mock_user = User(
            id=applicant_id,
            email="newapplicant@example.com",
            phone="1112223333",
            full_name="New Applicant",
        )
        mock_app = VolunteerApplication(
            id=uuid.uuid4(),
            user_id=applicant_id,
            status=ApplicationStatus.SUBMITTED,
            emergency_contact_name="New Applicant",
            emergency_contact_phone="1112223333",
        )

        with (
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_email",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_phone",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_default_role",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.create",
                AsyncMock(return_value=mock_user),
            ),
        ):
            mock_repo.create_application.return_value = None
            mock_repo.get_application_by_id.return_value = mock_app

            payload = VolunteerAdminIntakeRequest(
                full_name="New Applicant",
                email="newapplicant@example.com",
                phone="1112223333",
            )
            res = await svc.admin_volunteer_intake(payload, actor_id=coordinator_id)
            assert res.user_id == applicant_id
            assert res.user_id != coordinator_id

    @pytest.mark.asyncio
    async def test_admin_volunteer_intake_transaction_rollback_on_failure(self, mock_repo):
        coordinator_id = uuid.uuid4()
        svc = VolunteerService(mock_repo)

        mock_repo.create_application.side_effect = Exception("DB error during application insert")

        with (
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_email",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_by_phone",
                AsyncMock(return_value=None),
            ),
            patch(
                "pawguard.modules.auth.repository.UserRepository.get_default_role",
                AsyncMock(return_value=None),
            ),
            patch("pawguard.modules.auth.repository.UserRepository.create", AsyncMock()),
        ):
            payload = VolunteerAdminIntakeRequest(
                full_name="Test Fail",
                email="fail@example.com",
                phone="0000000000",
            )
            with pytest.raises(Exception, match="DB error"):
                await svc.admin_volunteer_intake(payload, actor_id=coordinator_id)

            mock_repo._session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        profile = VolunteerProfile(
            id=profile_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
            emergency_contact_name="Old",
            emergency_contact_phone="+1",
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]
        payload = VolunteerProfileUpdate(skills="Grooming")
        result = await service.update_profile(profile_id, payload)
        assert result.skills == "Grooming"

    @pytest.mark.asyncio
    async def test_update_profile_not_found(self, service, mock_repo):
        mock_repo.get_profile_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_profile(uuid.uuid4(), VolunteerProfileUpdate())

    @pytest.mark.asyncio
    async def test_approving_volunteer_grants_role(self, service, mock_repo):
        profile_id = uuid.uuid4()
        user_id = uuid.uuid4()
        profile = VolunteerProfile(
            id=profile_id,
            user_id=user_id,
            status=VolunteerStatus.APPLIED,
            emergency_contact_name="A",
            emergency_contact_phone="+1",
            background_check_completed=True,
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]

        volunteer_role = type("Role", (), {"id": uuid.uuid4(), "name": "volunteer"})()
        with (
            patch.object(service._roles, "get_by_name", AsyncMock(return_value=volunteer_role)),
            patch.object(service._user_roles, "grant_role", AsyncMock()) as mock_grant,
        ):
            await service.update_profile(
                profile_id, VolunteerProfileUpdate(status=VolunteerStatus.ACTIVE)
            )
            mock_grant.assert_awaited_once_with(user_id, volunteer_role.id)

    @pytest.mark.asyncio
    async def test_approval_notification_does_not_claim_shift_access(self, mock_repo):
        """Regression test: application approval creates the profile at
        APPLIED, not ACTIVE (activation is a separate coordinator step that
        also requires background_check_completed). The approval
        notification must not tell the applicant they can sign up for
        shifts yet - only that a background check comes next."""
        application_id = uuid.uuid4()
        user_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        mock_repo.get_application_by_id.return_value = VolunteerApplication(
            id=application_id,
            user_id=user_id,
            status=ApplicationStatus.SUBMITTED,
            emergency_contact_name="Jane",
            emergency_contact_phone="+123",
        )
        mock_repo.get_profile_by_user_id.return_value = None
        mock_repo.create_profile.return_value = None
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=profile_id,
            user_id=user_id,
            status=VolunteerStatus.APPLIED,
            emergency_contact_name="Jane",
            emergency_contact_phone="+123",
            user=Mock(email="jane@example.com"),
        )
        mock_notifications = AsyncMock()
        service = VolunteerService(mock_repo, notification_service=mock_notifications)

        await service.approve_application(application_id, reviewer_id=uuid.uuid4())

        mock_notifications.send_notification.assert_awaited_once()
        _, kwargs = mock_notifications.send_notification.call_args
        body = kwargs["payload"].body
        # The original bug: claiming immediate access before the profile is
        # even ONBOARDED, let alone ACTIVE.
        assert "you can now access the volunteer portal" not in body.lower()
        assert "background check" in body.lower()

    @pytest.mark.asyncio
    async def test_updating_profile_without_activating_does_not_grant_role(
        self, service, mock_repo
    ):
        profile_id = uuid.uuid4()
        profile = VolunteerProfile(
            id=profile_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.APPLIED,
            emergency_contact_name="A",
            emergency_contact_phone="+1",
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]

        with patch.object(service._user_roles, "grant_role", AsyncMock()) as mock_grant:
            await service.update_profile(profile_id, VolunteerProfileUpdate(skills="Grooming"))
            mock_grant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=profile_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
            emergency_contact_name="J",
            emergency_contact_phone="+1",
        )
        result = await service.get_profile(profile_id)
        assert result.id == profile_id

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, service, mock_repo):
        mock_repo.get_profile_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_profile(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_profile_by_user(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=uuid.uuid4(),
            user_id=user_id,
            status=VolunteerStatus.ACTIVE,
            emergency_contact_name="J",
            emergency_contact_phone="+1",
        )
        result = await service.get_profile_by_user(user_id)
        assert result.user_id == user_id

    @pytest.mark.asyncio
    async def test_get_profile_by_user_not_found(self, service, mock_repo):
        mock_repo.get_profile_by_user_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_profile_by_user(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_shift(self, service, mock_repo):
        shift_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.create_shift.return_value = VolunteerShift(
            id=shift_id,
            shelter_facility_id=uuid.uuid4(),
            role_name="Feeding",
            start_at=now,
            end_at=now,
            capacity=5,
        )
        payload = VolunteerShiftCreate(
            role_name="Feeding",
            start_at=now,
            end_at=now,
            capacity=5,
        )
        result = await service.create_shift(payload)
        assert result.role_name == "Feeding"

    @pytest.mark.asyncio
    async def test_join_shift(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id,
            role_name="Walking",
            start_at=now,
            end_at=now,
            capacity=5,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = None
        mock_repo.list_attendance_for_shift.return_value = []
        att_id = uuid.uuid4()
        mock_repo.create_attendance.return_value = ShiftAttendance(
            id=att_id,
            shift_id=shift_id,
            volunteer_id=uuid.uuid4(),
        )
        result = await service.join_shift(shift_id, volunteer_id)
        assert result.shift_id == shift_id

    @pytest.mark.asyncio
    async def test_join_shift_not_approved_forbidden(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.APPLIED,
        )
        with pytest.raises(ForbiddenError, match="approved by a coordinator"):
            await service.join_shift(shift_id, volunteer_id)

    @pytest.mark.asyncio
    async def test_join_shift_full(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id,
            role_name="Walking",
            start_at=now,
            end_at=now,
            capacity=1,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = None
        mock_repo.list_attendance_for_shift.return_value = [
            ShiftAttendance(
                id=uuid.uuid4(),
                shift_id=shift_id,
                volunteer_id=uuid.uuid4(),
            )
        ]
        with pytest.raises(ConflictError, match="maximum volunteer capacity"):
            await service.join_shift(shift_id, volunteer_id)

    @pytest.mark.asyncio
    async def test_join_shift_already_joined(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id,
            role_name="Walking",
            start_at=now,
            end_at=now,
            capacity=5,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = ShiftAttendance(
            id=uuid.uuid4(),
            shift_id=shift_id,
            volunteer_id=volunteer_id,
        )
        with pytest.raises(ConflictError, match="already joined"):
            await service.join_shift(shift_id, volunteer_id)

    @staticmethod
    def _user(user_id=None, *, can_manage_volunteers=False):
        """Lightweight `User` double for `has_permission()`, which reads
        `user.roles[*].permissions[*].code` (plus a `user_permissions`
        fallback the mock explicitly reports as absent via `spec`)."""
        permissions = [Mock(code="volunteer:update")] if can_manage_volunteers else []
        role = Mock(permissions=permissions)
        return Mock(spec=["id", "roles"], id=user_id or uuid.uuid4(), roles=[role])

    @pytest.mark.asyncio
    async def test_check_in(self, service, mock_repo):
        att_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        user = self._user()
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=user.id,
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=user.id,
            status=VolunteerStatus.ACTIVE,
        )
        result = await service.check_in(att_id, user)
        assert result.check_in_at is not None
        assert result.status == AttendanceStatus.CHECKED_IN

    @pytest.mark.asyncio
    async def test_check_in_another_volunteer_forbidden_without_permission(
        self, service, mock_repo
    ):
        """A volunteer with no `volunteer:update` permission cannot check in
        someone else's attendance - this is the ownership check that must
        stay intact; only a permitted coordinator/staff user bypasses it."""
        att_id = uuid.uuid4()
        user = self._user(can_manage_volunteers=False)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=uuid.uuid4(),
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        # The caller has no volunteer profile of their own at all - e.g. a
        # staff member who never applied to volunteer. Must fall through to
        # the permission check, not 404.
        mock_repo.get_profile_by_user_id.return_value = None
        with pytest.raises(ForbiddenError):
            await service.check_in(att_id, user)

    @pytest.mark.asyncio
    async def test_check_in_coordinator_can_check_in_another_volunteer(self, service, mock_repo):
        att_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        coordinator = self._user(can_manage_volunteers=True)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        # The coordinator has no volunteer profile of their own.
        mock_repo.get_profile_by_user_id.return_value = None
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
        )
        result = await service.check_in(att_id, coordinator)
        assert result.check_in_at is not None

    @pytest.mark.asyncio
    async def test_check_in_records_audit_for_coordinator_action(self, mock_repo):
        att_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        coordinator = self._user(can_manage_volunteers=True)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = None
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
        )
        mock_audit = AsyncMock(spec=AuditService)
        service = VolunteerService(mock_repo, audit_service=mock_audit)

        await service.check_in(att_id, coordinator, ip_address="10.0.0.5")

        mock_audit.record.assert_awaited_once()
        _, kwargs = mock_audit.record.call_args
        assert kwargs["actor_id"] == coordinator.id
        assert kwargs["metadata"]["action"] == "check_in"

    @pytest.mark.asyncio
    async def test_check_in_inactive_volunteer_forbidden(self, service, mock_repo):
        """Never activate/allow check-in before a cleared background check -
        an inactive volunteer must not be checked in even by a coordinator."""
        att_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        coordinator = self._user(can_manage_volunteers=True)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = None
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.INACTIVE,
        )
        with pytest.raises(ForbiddenError, match="not active"):
            await service.check_in(att_id, coordinator)

    @pytest.mark.asyncio
    async def test_check_in_missing_attendance_not_found(self, service, mock_repo):
        mock_repo.get_attendance_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.check_in(uuid.uuid4(), self._user())

    @pytest.mark.asyncio
    async def test_check_in_already_checked(self, service, mock_repo):
        volunteer_id = uuid.uuid4()
        user = self._user()
        attendance = ShiftAttendance(
            id=uuid.uuid4(),
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            check_in_at=datetime.now(UTC),
            status=AttendanceStatus.CHECKED_IN,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=user.id,
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=user.id,
            status=VolunteerStatus.ACTIVE,
        )
        with pytest.raises(ConflictError, match="Already checked in"):
            await service.check_in(uuid.uuid4(), user)

    @pytest.mark.asyncio
    async def test_check_out(self, service, mock_repo):
        att_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        user = self._user()
        check_in = datetime.now(UTC)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            check_in_at=check_in,
            status=AttendanceStatus.CHECKED_IN,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=user.id,
            status=VolunteerStatus.ACTIVE,
        )
        result = await service.check_out(att_id, user)
        assert result.check_out_at is not None
        assert result.hours_logged is not None
        assert result.status == AttendanceStatus.CHECKED_OUT

    @pytest.mark.asyncio
    async def test_check_out_coordinator_can_check_out_another_volunteer(self, service, mock_repo):
        att_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        coordinator = self._user(can_manage_volunteers=True)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            check_in_at=datetime.now(UTC),
            status=AttendanceStatus.CHECKED_IN,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = None
        result = await service.check_out(att_id, coordinator)
        assert result.check_out_at is not None

    @pytest.mark.asyncio
    async def test_check_out_unauthorized_staff_forbidden(self, service, mock_repo):
        att_id = uuid.uuid4()
        staff_without_permission = self._user(can_manage_volunteers=False)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=uuid.uuid4(),
            check_in_at=datetime.now(UTC),
            status=AttendanceStatus.CHECKED_IN,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = None
        with pytest.raises(ForbiddenError):
            await service.check_out(att_id, staff_without_permission)

    @pytest.mark.asyncio
    async def test_check_out_without_check_in(self, service, mock_repo):
        volunteer_id = uuid.uuid4()
        user = self._user()
        attendance = ShiftAttendance(
            id=uuid.uuid4(),
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=user.id,
            status=VolunteerStatus.ACTIVE,
        )
        with pytest.raises(ConflictError, match="check in before"):
            await service.check_out(uuid.uuid4(), user)

    @pytest.mark.asyncio
    async def test_check_out_already_checked(self, service, mock_repo):
        volunteer_id = uuid.uuid4()
        user = self._user()
        attendance = ShiftAttendance(
            id=uuid.uuid4(),
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            check_in_at=datetime.now(UTC),
            check_out_at=datetime.now(UTC),
            status=AttendanceStatus.CHECKED_OUT,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=user.id,
            status=VolunteerStatus.ACTIVE,
        )
        with pytest.raises(ConflictError, match="Already checked out"):
            await service.check_out(uuid.uuid4(), user)

    @pytest.mark.asyncio
    async def test_mark_no_show_by_coordinator(self, service, mock_repo):
        att_id = uuid.uuid4()
        coordinator = self._user(can_manage_volunteers=True)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=uuid.uuid4(),
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance

        result = await service.mark_no_show(att_id, coordinator, "Did not arrive.")

        assert result.status == AttendanceStatus.NO_SHOW
        assert result.no_show_reason == "Did not arrive."
        assert result.no_show_marked_by == coordinator.id

    @pytest.mark.asyncio
    async def test_mark_no_show_requires_permission(self, service, mock_repo):
        """No-show is never inferred and never self-service - only a
        coordinator/staff user with `volunteer:update` may mark one."""
        att_id = uuid.uuid4()
        volunteer = self._user(can_manage_volunteers=False)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=uuid.uuid4(),
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        with pytest.raises(ForbiddenError):
            await service.mark_no_show(att_id, volunteer, "Did not arrive.")

    @pytest.mark.asyncio
    async def test_mark_no_show_after_check_in_rejected(self, service, mock_repo):
        att_id = uuid.uuid4()
        coordinator = self._user(can_manage_volunteers=True)
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=uuid.uuid4(),
            check_in_at=datetime.now(UTC),
            status=AttendanceStatus.CHECKED_IN,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        with pytest.raises(ConflictError):
            await service.mark_no_show(att_id, coordinator, "Did not arrive.")

    @pytest.mark.asyncio
    async def test_cancel_attendance_self_service(self, service, mock_repo):
        att_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        user = self._user()
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            status=AttendanceStatus.CLAIMED,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=user.id, status=VolunteerStatus.ACTIVE
        )
        result = await service.cancel_attendance(att_id, user, "Scheduling conflict.")
        assert result.status == AttendanceStatus.CANCELLED
        assert result.cancelled_by == user.id

    @pytest.mark.asyncio
    async def test_cancel_attendance_after_check_in_rejected(self, service, mock_repo):
        att_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        user = self._user()
        attendance = ShiftAttendance(
            id=att_id,
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            check_in_at=datetime.now(UTC),
            status=AttendanceStatus.CHECKED_IN,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=user.id, status=VolunteerStatus.ACTIVE
        )
        with pytest.raises(ConflictError):
            await service.cancel_attendance(att_id, user, "Too late.")

    @pytest.mark.asyncio
    async def test_soft_delete_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=profile_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
            emergency_contact_name="J",
            emergency_contact_phone="+1",
        )
        mock_repo.soft_delete_profile.return_value = None
        await service.soft_delete_profile(profile_id)
        mock_repo.soft_delete_profile.assert_called_once_with(profile_id)

    @pytest.mark.asyncio
    async def test_soft_delete_profile_not_found(self, service, mock_repo):
        mock_repo.get_profile_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_profile(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_profiles(self, service, mock_repo):
        profile = VolunteerProfile(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
            emergency_contact_name="J",
            emergency_contact_phone="+1",
        )
        mock_repo.count_profiles.return_value = 1
        mock_repo.list_profiles.return_value = [profile]
        profiles, meta = await service.list_profiles()
        assert len(profiles) == 1
        assert meta.total == 1

    @pytest.mark.asyncio
    async def test_list_shifts(self, service, mock_repo):
        now = datetime.now(UTC)
        shift = VolunteerShift(
            id=uuid.uuid4(),
            role_name="Feeding",
            start_at=now,
            end_at=now,
            capacity=5,
        )
        mock_repo.count_shifts.return_value = 1
        mock_repo.list_shifts.return_value = [shift]
        shifts, meta = await service.list_shifts()
        assert len(shifts) == 1

    @pytest.mark.asyncio
    async def test_list_attendance(self, service, mock_repo):
        att = ShiftAttendance(id=uuid.uuid4(), shift_id=uuid.uuid4(), volunteer_id=uuid.uuid4())
        mock_repo.count_attendance_for_shift.return_value = 1
        mock_repo.list_attendance_for_shift.return_value = [att]
        records, meta = await service.list_attendance(uuid.uuid4())
        assert len(records) == 1


class TestServiceCertificate:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=VolunteerRepository)
        repo._session = AsyncMock()
        # `session.add` is synchronous; keep it a plain Mock so the service's
        # synchronous `.add(stored)` call doesn't leak an un-awaited coroutine.
        repo._session.add = Mock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return VolunteerService(mock_repo, audit_service=mock_audit)

    def _profile(self, **kw):
        vals = dict(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
            emergency_contact_name="Jane",
            emergency_contact_phone="+1",
            user=User(
                id=kw.get("user_id", uuid.uuid4()), full_name="Jane Doe", email="jane@example.com"
            ),
        )
        vals.update(kw)
        return VolunteerProfile(**vals)

    def _attendance(self, volunteer_id, hours, role="Walking", **kw):
        now = datetime.now(UTC)
        return ShiftAttendance(
            id=uuid.uuid4(),
            shift_id=uuid.uuid4(),
            volunteer_id=volunteer_id,
            check_in_at=now,
            check_out_at=now,
            hours_logged=hours,
            shift=VolunteerShift(id=uuid.uuid4(), role_name=role, start_at=now, end_at=now),
            **kw,
        )

    @pytest.mark.asyncio
    async def test_get_service_summary(self, service, mock_repo):
        profile = self._profile()
        mock_repo.get_profile_by_id.return_value = profile
        mock_repo.list_attendance_for_volunteer.return_value = [
            self._attendance(profile.id, 2.0, role="Walking"),
            self._attendance(profile.id, 3.5, role="Feeding"),
        ]
        summary = await service.get_service_summary(profile.id)
        assert summary.total_hours == 5.5
        assert summary.shifts_count == 2
        assert summary.role_summary == "Feeding, Walking"

    @pytest.mark.asyncio
    async def test_issue_certificate_success(self, service, mock_repo, mock_audit):
        profile = self._profile()
        mock_repo.get_profile_by_id.return_value = profile
        mock_repo.list_attendance_for_volunteer.return_value = [
            self._attendance(profile.id, 3.0, role="Walking"),
        ]
        mock_storage = AsyncMock(spec=StorageService)
        mock_storage.build_object_key.return_value = "certificates/service_certificate_test.pdf"
        mock_storage.put_object.return_value = None

        pdf_bytes, object_key = await service.issue_service_certificate(
            profile.id,
            actor_id=uuid.uuid4(),
            ip_address="203.0.113.9",
            storage_service=mock_storage,
        )
        assert len(pdf_bytes) > 0
        assert object_key == "certificates/service_certificate_test.pdf"
        assert profile.is_certified is True
        assert profile.certificate_issued_at is not None
        assert profile.certificate_object_key == "certificates/service_certificate_test.pdf"
        mock_storage.put_object.assert_called_once()
        assert mock_storage.put_object.call_args.kwargs["content_type"] == "application/pdf"
        mock_audit.record.assert_awaited_once()
        kwargs = mock_audit.record.call_args.kwargs
        assert kwargs["event_type"].value == "volunteer_certificate_issued"
        assert kwargs["metadata"]["total_hours"] == "3.0"
        assert kwargs["metadata"]["shifts_count"] == 1

    @pytest.mark.asyncio
    async def test_get_service_certificate_not_issued(self, service, mock_repo):
        profile = self._profile(is_certified=False, certificate_object_key=None)
        mock_repo.get_profile_by_id.return_value = profile
        mock_storage = AsyncMock(spec=StorageService)

        with pytest.raises(NotFoundError, match="No service certificate has been issued"):
            await service.get_service_certificate(profile.id, storage_service=mock_storage)

        mock_storage.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_service_certificate_issued_success(self, service, mock_repo):
        object_key = "certificates/service_certificate_test.pdf"
        profile = self._profile(is_certified=True, certificate_object_key=object_key)
        mock_repo.get_profile_by_id.return_value = profile
        mock_storage = Mock(spec=StorageService)
        mock_storage.generate_presigned_download_url.return_value = (
            "https://s3.example.com/download.pdf"
        )

        res = await service.get_service_certificate(profile.id, storage_service=mock_storage)

        assert res.download_url == "https://s3.example.com/download.pdf"
        assert res.object_key == object_key
        assert res.file_id == profile.id
        mock_storage.generate_presigned_download_url.assert_called_once_with(object_key=object_key)
        # Verify no put_object (write) was called
        assert not hasattr(mock_storage, "put_object") or not mock_storage.put_object.called

    @pytest.mark.asyncio
    async def test_issue_certificate_no_shifts(self, service, mock_repo):
        profile = self._profile()
        mock_repo.get_profile_by_id.return_value = profile
        mock_repo.list_attendance_for_volunteer.return_value = []
        with pytest.raises(ValidationFailedError, match="at least one attended shift"):
            await service.issue_service_certificate(profile.id)

    @pytest.mark.asyncio
    async def test_issue_certificate_profile_not_found(self, service, mock_repo):
        mock_repo.get_profile_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.issue_service_certificate(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_all_attendance_for_volunteer(self, service, mock_repo):
        profile = self._profile()
        expected = [
            self._attendance(profile.id, 2.0, role="Walking"),
            self._attendance(profile.id, 0.0, role="Feeding"),
        ]
        mock_repo.list_all_attendance_for_volunteer.return_value = expected
        result = await service.list_all_attendance_for_volunteer(profile.id)
        assert len(result) == 2
        assert result == expected
        mock_repo.list_all_attendance_for_volunteer.assert_called_once_with(profile.id)


class TestVolunteerShiftAssignment:
    """Authoritative test suite for Volunteer Coordinator shift assignment (Volunteer Bug #1)."""

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=VolunteerRepository)
        repo._session = AsyncMock()
        repo._session.add = Mock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return VolunteerService(mock_repo, audit_service=mock_audit)

    # ── TEST A: Volunteer Coordinator assigns approved volunteer → SUCCESS ─
    @pytest.mark.asyncio
    async def test_assign_approved_volunteer_by_profile_id_success(
        self, service, mock_repo, mock_audit
    ):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        user_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_profile = VolunteerProfile(
            id=volunteer_id,
            user_id=user_id,
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_profile_by_id.return_value = mock_profile
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id,
            role_name="Feeding & Cleaning",
            start_at=now,
            end_at=now,
            capacity=5,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = None
        mock_repo.list_attendance_for_shift.return_value = []

        att_id = uuid.uuid4()
        mock_repo.create_attendance.return_value = ShiftAttendance(
            id=att_id,
            shift_id=shift_id,
            volunteer_id=volunteer_id,
            status=AttendanceStatus.CLAIMED,
        )

        result = await service.assign_volunteer_to_shift(
            shift_id=shift_id,
            volunteer_target_id=volunteer_id,
            actor_id=actor_id,
            ip_address="192.168.1.1",
        )

        assert result.id == att_id
        assert result.shift_id == shift_id
        assert result.volunteer_id == volunteer_id
        assert result.status == AttendanceStatus.CLAIMED
        mock_repo.create_attendance.assert_awaited_once()
        mock_audit.record.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assign_approved_volunteer_by_user_id_fallback_success(self, service, mock_repo):
        shift_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_profile = VolunteerProfile(
            id=profile_id,
            user_id=user_id,
            status=VolunteerStatus.ACTIVE,
        )
        # ID lookup returns None, user_id lookup succeeds
        mock_repo.get_profile_by_id.return_value = None
        mock_repo.get_profile_by_user_id.return_value = mock_profile
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id,
            role_name="Dog Walking",
            start_at=now,
            end_at=now,
            capacity=3,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = None
        mock_repo.list_attendance_for_shift.return_value = []

        mock_repo.create_attendance.return_value = ShiftAttendance(
            id=uuid.uuid4(),
            shift_id=shift_id,
            volunteer_id=profile_id,
            status=AttendanceStatus.CLAIMED,
        )

        result = await service.assign_volunteer_to_shift(
            shift_id=shift_id,
            volunteer_target_id=user_id,
        )
        assert result.volunteer_id == profile_id
        mock_repo.create_attendance.assert_awaited_once()

    # ── TEST B: Same volunteer assigned again → correctly rejected ─────────
    @pytest.mark.asyncio
    async def test_assign_duplicate_volunteer_rejected(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id,
            role_name="Walking",
            start_at=now,
            end_at=now,
            capacity=5,
        )
        # Already enrolled
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = ShiftAttendance(
            id=uuid.uuid4(),
            shift_id=shift_id,
            volunteer_id=volunteer_id,
            status=AttendanceStatus.CLAIMED,
        )

        with pytest.raises(ConflictError, match="already been assigned"):
            await service.assign_volunteer_to_shift(
                shift_id=shift_id,
                volunteer_target_id=volunteer_id,
            )
        mock_repo.create_attendance.assert_not_called()

    # ── TEST C: Shift at capacity → correctly rejected ─────────────────────
    @pytest.mark.asyncio
    async def test_assign_shift_at_capacity_rejected(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id,
            role_name="Walking",
            start_at=now,
            end_at=now,
            capacity=2,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = None
        mock_repo.list_attendance_for_shift.return_value = [
            ShiftAttendance(
                id=uuid.uuid4(),
                shift_id=shift_id,
                volunteer_id=uuid.uuid4(),
                status=AttendanceStatus.CLAIMED,
            ),
            ShiftAttendance(
                id=uuid.uuid4(),
                shift_id=shift_id,
                volunteer_id=uuid.uuid4(),
                status=AttendanceStatus.CLAIMED,
            ),
        ]

        with pytest.raises(ConflictError, match="maximum volunteer capacity"):
            await service.assign_volunteer_to_shift(
                shift_id=shift_id,
                volunteer_target_id=volunteer_id,
            )
        mock_repo.create_attendance.assert_not_called()

    # ── TEST D: Unapproved volunteer → correctly rejected ───────────────────
    @pytest.mark.asyncio
    async def test_assign_unapproved_volunteer_rejected(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()

        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.APPLIED,  # Not ACTIVE/approved
        )

        with pytest.raises(ValidationFailedError, match="approved/active volunteers"):
            await service.assign_volunteer_to_shift(
                shift_id=shift_id,
                volunteer_target_id=volunteer_id,
            )
        mock_repo.get_shift_by_id_for_update.assert_not_called()
        mock_repo.create_attendance.assert_not_called()

    # ── Non-existent volunteer / shift ─────────────────────────────────────
    @pytest.mark.asyncio
    async def test_assign_non_existent_volunteer_raises_not_found(self, service, mock_repo):
        mock_repo.get_profile_by_id.return_value = None
        mock_repo.get_profile_by_user_id.return_value = None
        with pytest.raises(NotFoundError, match="Volunteer profile not found"):
            await service.assign_volunteer_to_shift(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_assign_non_existent_shift_raises_not_found(self, service, mock_repo):
        volunteer_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id,
            user_id=uuid.uuid4(),
            status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = None
        with pytest.raises(NotFoundError, match="Volunteer shift not found"):
            await service.assign_volunteer_to_shift(uuid.uuid4(), volunteer_id)


class TestVolunteerShiftAssignmentRouter:
    """Router-level contract tests for POST /api/v1/volunteers/shifts/{shift_id}/assign and /join."""

    @pytest.mark.asyncio
    async def test_router_coordinator_assign_volunteer_success(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from pawguard.core.exceptions import register_exception_handlers
        from pawguard.core.security import AccessTokenClaims
        from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
        from pawguard.modules.volunteer.router import get_volunteer_service, router

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1")

        coordinator_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_user_obj = User(
            id=coordinator_id,
            email="coordinator@pawguard.org",
            full_name="Volunteer Coordinator",
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
                user_id=coordinator_id,
                session_id=uuid.uuid4(),
                roles=["super_admin"],
                jti=str(uuid.uuid4()),
                expires_at=datetime.now(UTC),
            ),
            db=AsyncMock(),
            redis=AsyncMock(),
        )

        mock_svc = AsyncMock(spec=VolunteerService)
        shift_id = uuid.uuid4()
        vol_id = uuid.uuid4()
        att_id = uuid.uuid4()
        mock_svc.assign_volunteer_to_shift.return_value = ShiftAttendance(
            id=att_id,
            shift_id=shift_id,
            volunteer_id=vol_id,
            status=AttendanceStatus.CLAIMED,
            created_at=now,
            updated_at=now,
        )

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_volunteer_service] = lambda: mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/volunteers/shifts/{shift_id}/assign",
                json={"volunteer_id": str(vol_id)},
            )
            assert resp.status_code == 201
            data = resp.json()["data"]
            assert data["id"] == str(att_id)
            assert data["shift_id"] == str(shift_id)
            assert data["volunteer_id"] == str(vol_id)
            assert data["status"] == "claimed"

    @pytest.mark.asyncio
    async def test_router_normal_volunteer_cannot_call_assign_endpoint(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from pawguard.core.exceptions import register_exception_handlers
        from pawguard.core.security import AccessTokenClaims
        from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
        from pawguard.modules.volunteer.router import get_volunteer_service, router

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1")

        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_user_obj = User(
            id=volunteer_id,
            email="volunteer@example.com",
            full_name="Regular Volunteer",
            phone="+919876543210",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
            mfa_enabled=False,
            created_at=now,
            updated_at=now,
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_user = CurrentUser(
            user=mock_user_obj,
            claims=AccessTokenClaims(
                user_id=volunteer_id,
                session_id=uuid.uuid4(),
                roles=["volunteer"],
                jti=str(uuid.uuid4()),
                expires_at=datetime.now(UTC),
            ),
            db=AsyncMock(),
            redis=mock_redis,
        )

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_volunteer_service] = lambda: AsyncMock(spec=VolunteerService)

        with (
            patch(
                "pawguard.modules.auth.rbac.get_role_permission_codes",
                AsyncMock(return_value={"volunteer:read"}),
            ),
            patch(
                "pawguard.modules.auth.rbac.get_user_permission_codes",
                AsyncMock(return_value=set()),
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/volunteers/shifts/{uuid.uuid4()}/assign",
                    json={"volunteer_id": str(uuid.uuid4())},
                )
                assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_router_normal_volunteer_can_still_self_join_shift(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from pawguard.core.security import AccessTokenClaims
        from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
        from pawguard.modules.volunteer.router import get_volunteer_service, router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        user_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        shift_id = uuid.uuid4()
        att_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_user_obj = User(
            id=user_id,
            email="volunteer@example.com",
            full_name="Regular Volunteer",
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
                roles=["volunteer"],
                jti=str(uuid.uuid4()),
                expires_at=datetime.now(UTC),
            ),
            db=AsyncMock(),
            redis=AsyncMock(),
        )

        mock_svc = AsyncMock(spec=VolunteerService)
        mock_svc.get_profile_by_user.return_value = VolunteerProfile(
            id=profile_id,
            user_id=user_id,
            status=VolunteerStatus.ACTIVE,
        )
        mock_svc.join_shift.return_value = ShiftAttendance(
            id=att_id,
            shift_id=shift_id,
            volunteer_id=profile_id,
            status=AttendanceStatus.CLAIMED,
            created_at=now,
            updated_at=now,
        )

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_volunteer_service] = lambda: mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/v1/volunteers/shifts/{shift_id}/join")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["id"] == str(att_id)
            assert data["shift_id"] == str(shift_id)
            assert data["volunteer_id"] == str(profile_id)
