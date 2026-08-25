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
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=volunteer_id, status=AttendanceStatus.CLAIMED
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
    async def test_check_in_another_volunteer_forbidden_without_permission(self, service, mock_repo):
        """A volunteer with no `volunteer:update` permission cannot check in
        someone else's attendance - this is the ownership check that must
        stay intact; only a permitted coordinator/staff user bypasses it."""
        att_id = uuid.uuid4()
        user = self._user(can_manage_volunteers=False)
        attendance = ShiftAttendance(
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=uuid.uuid4(), status=AttendanceStatus.CLAIMED
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
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=volunteer_id, status=AttendanceStatus.CLAIMED
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
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=volunteer_id, status=AttendanceStatus.CLAIMED
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
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=volunteer_id, status=AttendanceStatus.CLAIMED
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
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=uuid.uuid4(), status=AttendanceStatus.CLAIMED
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
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=uuid.uuid4(), status=AttendanceStatus.CLAIMED
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
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=volunteer_id, status=AttendanceStatus.CLAIMED
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
        mock_storage.put_object.assert_called_once()
        assert mock_storage.put_object.call_args.kwargs["content_type"] == "application/pdf"
        mock_audit.record.assert_awaited_once()
        kwargs = mock_audit.record.call_args.kwargs
        assert kwargs["event_type"].value == "volunteer_certificate_issued"
        assert kwargs["metadata"]["total_hours"] == "3.0"
        assert kwargs["metadata"]["shifts_count"] == 1

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
