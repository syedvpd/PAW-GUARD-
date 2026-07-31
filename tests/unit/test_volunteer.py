"""Unit tests for VolunteerService with mocked repository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from pawguard.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from pawguard.modules.volunteer.models import (
    ShiftAttendance,
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


class TestVolunteerService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=VolunteerRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return VolunteerService(mock_repo)

    @pytest.mark.asyncio
    async def test_apply_to_volunteer(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_profile_by_user_id.return_value = None
        profile_id = uuid.uuid4()
        mock_repo.create_profile.return_value = None
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=profile_id, user_id=user_id, status=VolunteerStatus.APPLIED,
            emergency_contact_name="Jane", emergency_contact_phone="+123",
        )
        payload = VolunteerProfileCreate(
            emergency_contact_name="Jane", emergency_contact_phone="+123",
        )
        result = await service.apply_to_volunteer(user_id, payload)
        assert result.status == VolunteerStatus.APPLIED

    @pytest.mark.asyncio
    async def test_apply_to_volunteer_already_exists(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=uuid.uuid4(), user_id=user_id, status=VolunteerStatus.APPLIED,
            emergency_contact_name="Jane", emergency_contact_phone="+123",
        )
        with pytest.raises(ConflictError, match="already applied"):
            await service.apply_to_volunteer(user_id, VolunteerProfileCreate(
                emergency_contact_name="Jane", emergency_contact_phone="+123",
            ))

    @pytest.mark.asyncio
    async def test_update_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        profile = VolunteerProfile(
            id=profile_id, user_id=uuid.uuid4(), status=VolunteerStatus.ACTIVE,
            emergency_contact_name="Old", emergency_contact_phone="+1",
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
            id=profile_id, user_id=user_id, status=VolunteerStatus.APPLIED,
            emergency_contact_name="A", emergency_contact_phone="+1",
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]

        volunteer_role = type("Role", (), {"id": uuid.uuid4(), "name": "volunteer"})()
        with (
            patch.object(service._roles, "get_by_name", AsyncMock(return_value=volunteer_role)),
            patch.object(service._user_roles, "grant_role", AsyncMock()) as mock_grant,
        ):
            await service.update_profile(profile_id, VolunteerProfileUpdate(status=VolunteerStatus.ACTIVE))
            mock_grant.assert_awaited_once_with(user_id, volunteer_role.id)

    @pytest.mark.asyncio
    async def test_updating_profile_without_activating_does_not_grant_role(self, service, mock_repo):
        profile_id = uuid.uuid4()
        profile = VolunteerProfile(
            id=profile_id, user_id=uuid.uuid4(), status=VolunteerStatus.APPLIED,
            emergency_contact_name="A", emergency_contact_phone="+1",
        )
        mock_repo.get_profile_by_id.side_effect = [profile, profile]

        with patch.object(service._user_roles, "grant_role", AsyncMock()) as mock_grant:
            await service.update_profile(profile_id, VolunteerProfileUpdate(skills="Grooming"))
            mock_grant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=profile_id, user_id=uuid.uuid4(), status=VolunteerStatus.ACTIVE,
            emergency_contact_name="J", emergency_contact_phone="+1",
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
            id=uuid.uuid4(), user_id=user_id, status=VolunteerStatus.ACTIVE,
            emergency_contact_name="J", emergency_contact_phone="+1",
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
            id=shift_id, shelter_facility_id=uuid.uuid4(), role_name="Feeding",
            start_at=now, end_at=now, capacity=5,
        )
        payload = VolunteerShiftCreate(
            role_name="Feeding", start_at=now, end_at=now, capacity=5,
        )
        result = await service.create_shift(payload)
        assert result.role_name == "Feeding"

    @pytest.mark.asyncio
    async def test_join_shift(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=uuid.uuid4(), status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id, role_name="Walking", start_at=now, end_at=now, capacity=5,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = None
        mock_repo.list_attendance_for_shift.return_value = []
        att_id = uuid.uuid4()
        mock_repo.create_attendance.return_value = ShiftAttendance(
            id=att_id, shift_id=shift_id, volunteer_id=uuid.uuid4(),
        )
        result = await service.join_shift(shift_id, volunteer_id)
        assert result.shift_id == shift_id

    @pytest.mark.asyncio
    async def test_join_shift_not_approved_forbidden(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=uuid.uuid4(), status=VolunteerStatus.APPLIED,
        )
        with pytest.raises(ForbiddenError, match="approved by a coordinator"):
            await service.join_shift(shift_id, volunteer_id)

    @pytest.mark.asyncio
    async def test_join_shift_full(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=uuid.uuid4(), status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id, role_name="Walking", start_at=now, end_at=now, capacity=1,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = None
        mock_repo.list_attendance_for_shift.return_value = [ShiftAttendance(
            id=uuid.uuid4(), shift_id=shift_id, volunteer_id=uuid.uuid4(),
        )]
        with pytest.raises(ConflictError, match="maximum volunteer capacity"):
            await service.join_shift(shift_id, volunteer_id)

    @pytest.mark.asyncio
    async def test_join_shift_already_joined(self, service, mock_repo):
        shift_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=uuid.uuid4(), status=VolunteerStatus.ACTIVE,
        )
        mock_repo.get_shift_by_id_for_update.return_value = VolunteerShift(
            id=shift_id, role_name="Walking", start_at=now, end_at=now, capacity=5,
        )
        mock_repo.get_attendance_by_shift_and_volunteer.return_value = ShiftAttendance(
            id=uuid.uuid4(), shift_id=shift_id, volunteer_id=volunteer_id,
        )
        with pytest.raises(ConflictError, match="already joined"):
            await service.join_shift(shift_id, volunteer_id)

    @pytest.mark.asyncio
    async def test_check_in(self, service, mock_repo):
        att_id = uuid.uuid4()
        user_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        attendance = ShiftAttendance(id=att_id, shift_id=uuid.uuid4(), volunteer_id=volunteer_id)
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=user_id, status=VolunteerStatus.ACTIVE,
        )
        result = await service.check_in(att_id, user_id)
        assert result.check_in_at is not None

    @pytest.mark.asyncio
    async def test_check_in_wrong_owner_forbidden(self, service, mock_repo):
        att_id = uuid.uuid4()
        user_id = uuid.uuid4()
        attendance = ShiftAttendance(id=att_id, shift_id=uuid.uuid4(), volunteer_id=uuid.uuid4())
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=uuid.uuid4(), user_id=user_id, status=VolunteerStatus.ACTIVE,
        )
        with pytest.raises(ForbiddenError):
            await service.check_in(att_id, user_id)

    @pytest.mark.asyncio
    async def test_check_in_already_checked(self, service, mock_repo):
        user_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        attendance = ShiftAttendance(
            id=uuid.uuid4(), shift_id=uuid.uuid4(), volunteer_id=volunteer_id,
            check_in_at=datetime.now(UTC),
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=user_id, status=VolunteerStatus.ACTIVE,
        )
        with pytest.raises(ConflictError, match="Already checked in"):
            await service.check_in(uuid.uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_check_out(self, service, mock_repo):
        att_id = uuid.uuid4()
        user_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        check_in = datetime.now(UTC)
        attendance = ShiftAttendance(
            id=att_id, shift_id=uuid.uuid4(), volunteer_id=volunteer_id,
            check_in_at=check_in,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=user_id, status=VolunteerStatus.ACTIVE,
        )
        result = await service.check_out(att_id, user_id)
        assert result.check_out_at is not None
        assert result.hours_logged is not None

    @pytest.mark.asyncio
    async def test_check_out_without_check_in(self, service, mock_repo):
        user_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        attendance = ShiftAttendance(
            id=uuid.uuid4(), shift_id=uuid.uuid4(), volunteer_id=volunteer_id,
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=user_id, status=VolunteerStatus.ACTIVE,
        )
        with pytest.raises(ConflictError, match="check in before"):
            await service.check_out(uuid.uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_check_out_already_checked(self, service, mock_repo):
        user_id = uuid.uuid4()
        volunteer_id = uuid.uuid4()
        attendance = ShiftAttendance(
            id=uuid.uuid4(), shift_id=uuid.uuid4(), volunteer_id=volunteer_id,
            check_in_at=datetime.now(UTC), check_out_at=datetime.now(UTC),
        )
        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = VolunteerProfile(
            id=volunteer_id, user_id=user_id, status=VolunteerStatus.ACTIVE,
        )
        with pytest.raises(ConflictError, match="Already checked out"):
            await service.check_out(uuid.uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_soft_delete_profile(self, service, mock_repo):
        profile_id = uuid.uuid4()
        mock_repo.get_profile_by_id.return_value = VolunteerProfile(
            id=profile_id, user_id=uuid.uuid4(), status=VolunteerStatus.ACTIVE,
            emergency_contact_name="J", emergency_contact_phone="+1",
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
            id=uuid.uuid4(), user_id=uuid.uuid4(), status=VolunteerStatus.ACTIVE,
            emergency_contact_name="J", emergency_contact_phone="+1",
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
            id=uuid.uuid4(), role_name="Feeding", start_at=now, end_at=now, capacity=5,
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
