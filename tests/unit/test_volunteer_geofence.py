"""Unit tests for Volunteer Shift GPS Geofencing (Check-In & Check-Out)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ValidationFailedError
from pawguard.modules.volunteer.models import (
    AttendanceStatus,
    ShiftAttendance,
    VolunteerProfile,
    VolunteerShift,
    VolunteerStatus,
)
from pawguard.modules.volunteer.repository import VolunteerRepository
from pawguard.modules.volunteer.service import (
    VolunteerService,
    calculate_haversine_distance_meters,
)


class TestHaversineDistance:
    def test_same_point_returns_zero(self):
        dist = calculate_haversine_distance_meters(17.4482, 78.3741, 17.4482, 78.3741)
        assert round(dist, 2) == 0.0

    def test_known_distance(self):
        # Point A: 17.4482, 78.3741
        # Point B: ~100m away (17.4491, 78.3741)
        dist = calculate_haversine_distance_meters(17.4482, 78.3741, 17.4491, 78.3741)
        assert 95.0 <= dist <= 105.0


class TestVolunteerGeofencing:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=VolunteerRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return VolunteerService(
            repository=mock_repo,
            audit_service=None,
            notification_service=None,
        )

    @pytest.fixture
    def active_volunteer(self):
        user = MagicMock()
        user.id = uuid.uuid4()

        profile = MagicMock(spec=VolunteerProfile)
        profile.id = uuid.uuid4()
        profile.user_id = user.id
        profile.status = VolunteerStatus.ACTIVE
        return user, profile

    @pytest.fixture
    def geofenced_shift(self):
        shift = MagicMock(spec=VolunteerShift)
        shift.id = uuid.uuid4()
        shift.shelter_facility_id = None
        shift.latitude = 17.4482
        shift.longitude = 78.3741
        shift.allowed_radius_meters = 500
        return shift

    @pytest.mark.asyncio
    async def test_check_in_inside_geofence_succeeds(
        self, service, mock_repo, active_volunteer, geofenced_shift
    ):
        user, profile = active_volunteer
        attendance_id = uuid.uuid4()

        attendance = ShiftAttendance(
            id=attendance_id,
            shift_id=geofenced_shift.id,
            volunteer_id=profile.id,
            status=AttendanceStatus.CLAIMED,
        )

        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = profile
        mock_repo.get_profile_by_id.return_value = profile
        mock_repo.get_shift_by_id.return_value = geofenced_shift

        # Volunteer location ~100m away (inside 500m radius)
        result = await service.check_in(
            attendance_id,
            user,
            latitude=17.4485,
            longitude=78.3741,
        )

        assert result.status == AttendanceStatus.CHECKED_IN
        assert result.check_in_lat == 17.4485
        assert result.check_in_lng == 78.3741
        assert result.check_in_distance_meters is not None
        assert result.check_in_distance_meters <= 500.0

    @pytest.mark.asyncio
    async def test_check_in_outside_geofence_rejected(
        self, service, mock_repo, active_volunteer, geofenced_shift
    ):
        user, profile = active_volunteer
        attendance_id = uuid.uuid4()

        attendance = ShiftAttendance(
            id=attendance_id,
            shift_id=geofenced_shift.id,
            volunteer_id=profile.id,
            status=AttendanceStatus.CLAIMED,
        )

        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = profile
        mock_repo.get_profile_by_id.return_value = profile
        mock_repo.get_shift_by_id.return_value = geofenced_shift

        # Volunteer location ~2000m away (outside 500m radius)
        with pytest.raises(ValidationFailedError, match="exceeds the allowed geofence radius"):
            await service.check_in(
                attendance_id,
                user,
                latitude=17.4662,
                longitude=78.3741,
            )

        # Ensure attendance record was NOT updated
        assert attendance.status == AttendanceStatus.CLAIMED

    @pytest.mark.asyncio
    async def test_check_in_missing_gps_on_geofenced_shift_rejected(
        self, service, mock_repo, active_volunteer, geofenced_shift
    ):
        user, profile = active_volunteer
        attendance_id = uuid.uuid4()

        attendance = ShiftAttendance(
            id=attendance_id,
            shift_id=geofenced_shift.id,
            volunteer_id=profile.id,
            status=AttendanceStatus.CLAIMED,
        )

        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = profile
        mock_repo.get_profile_by_id.return_value = profile
        mock_repo.get_shift_by_id.return_value = geofenced_shift

        with pytest.raises(ValidationFailedError, match="GPS coordinates .* are required"):
            await service.check_in(
                attendance_id,
                user,
                latitude=None,
                longitude=None,
            )

    @pytest.mark.asyncio
    async def test_check_in_legacy_shift_without_geofence_succeeds(
        self, service, mock_repo, active_volunteer
    ):
        user, profile = active_volunteer
        attendance_id = uuid.uuid4()

        legacy_shift = MagicMock(spec=VolunteerShift)
        legacy_shift.id = uuid.uuid4()
        legacy_shift.shelter_facility_id = None
        legacy_shift.latitude = None
        legacy_shift.longitude = None

        attendance = ShiftAttendance(
            id=attendance_id,
            shift_id=legacy_shift.id,
            volunteer_id=profile.id,
            status=AttendanceStatus.CLAIMED,
        )

        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = profile
        mock_repo.get_profile_by_id.return_value = profile
        mock_repo.get_shift_by_id.return_value = legacy_shift

        # Legacy shift without geofence allows check-in without coordinates
        result = await service.check_in(attendance_id, user)
        assert result.status == AttendanceStatus.CHECKED_IN

    @pytest.mark.asyncio
    async def test_check_out_inside_geofence_succeeds(
        self, service, mock_repo, active_volunteer, geofenced_shift
    ):
        user, profile = active_volunteer
        attendance_id = uuid.uuid4()

        attendance = ShiftAttendance(
            id=attendance_id,
            shift_id=geofenced_shift.id,
            volunteer_id=profile.id,
            status=AttendanceStatus.CHECKED_IN,
            check_in_at=datetime.now(UTC),
        )

        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = profile
        mock_repo.get_shift_by_id.return_value = geofenced_shift

        result = await service.check_out(
            attendance_id,
            user,
            latitude=17.4482,
            longitude=78.3741,
        )

        assert result.status == AttendanceStatus.CHECKED_OUT
        assert result.check_out_lat == 17.4482
        assert result.check_out_lng == 78.3741

    @pytest.mark.asyncio
    async def test_check_out_outside_geofence_rejected(
        self, service, mock_repo, active_volunteer, geofenced_shift
    ):
        user, profile = active_volunteer
        attendance_id = uuid.uuid4()

        attendance = ShiftAttendance(
            id=attendance_id,
            shift_id=geofenced_shift.id,
            volunteer_id=profile.id,
            status=AttendanceStatus.CHECKED_IN,
            check_in_at=datetime.now(UTC),
        )

        mock_repo.get_attendance_by_id.return_value = attendance
        mock_repo.get_profile_by_user_id.return_value = profile
        mock_repo.get_shift_by_id.return_value = geofenced_shift

        with pytest.raises(ValidationFailedError, match="exceeds the allowed geofence radius"):
            await service.check_out(
                attendance_id,
                user,
                latitude=17.4662,
                longitude=78.3741,
            )

        assert attendance.status == AttendanceStatus.CHECKED_IN
