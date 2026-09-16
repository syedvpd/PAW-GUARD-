"""Tests for Volunteer Shift Capacity Trigger and Enforcement (ITEM 9d).

Verifies:
1. DB Trigger: trg_check_shift_capacity rejects an INSERT into shift_attendances when non-cancelled attendances reach shift capacity (PostgreSQL).
2. Service Level: VolunteerService rejects shift join when active attendances >= capacity.
3. Cancellation: Cancelled attendance frees a capacity slot and allows a new volunteer to claim the shift.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ConflictError
from pawguard.modules.auth.models import User
from pawguard.modules.volunteer.models import (
    AttendanceStatus,
    ShiftAttendance,
    VolunteerProfile,
    VolunteerShift,
    VolunteerStatus,
)
from pawguard.modules.volunteer.repository import VolunteerRepository
from pawguard.modules.volunteer.service import VolunteerService


@pytest.mark.asyncio
async def test_volunteer_shift_capacity_trigger_enforcement(
    db_session: AsyncSession,
) -> None:
    """Tests the database trigger trg_check_shift_capacity directly on PostgreSQL, or skips if SQLite."""
    if db_session.bind and db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required to test database-level trigger trg_check_shift_capacity")

    # 1. Create a volunteer shift with capacity = 2
    shift_id = uuid.uuid4()
    shift = VolunteerShift(
        id=shift_id,
        role_name="Dog Walking",
        start_at=datetime.now(UTC),
        end_at=datetime.now(UTC) + timedelta(hours=2),
        capacity=2,
    )
    db_session.add(shift)

    # 2. Create 3 volunteers
    v1_id, v2_id, v3_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    u1_id, u2_id, u3_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    for uid, vid, email in [
        (u1_id, v1_id, f"vol1_{v1_id.hex[:6]}@example.com"),
        (u2_id, v2_id, f"vol2_{v2_id.hex[:6]}@example.com"),
        (u3_id, v3_id, f"vol3_{v3_id.hex[:6]}@example.com"),
    ]:
        user = User(
            id=uid,
            email=email,
            hashed_password="pw",
            full_name="Vol",
            system_role="volunteer",
            is_active=True,
        )
        db_session.add(user)
        vprof = VolunteerProfile(
            id=vid,
            user_id=uid,
            skills=["handling"],
        )
        db_session.add(vprof)

    await db_session.flush()

    # 3. Insert Attendance 1 (capacity: 1/2) -> SUCCESS
    att1 = ShiftAttendance(
        id=uuid.uuid4(),
        shift_id=shift_id,
        volunteer_id=v1_id,
        status=AttendanceStatus.CLAIMED,
    )
    db_session.add(att1)
    await db_session.flush()

    # 4. Insert Attendance 2 (capacity: 2/2) -> SUCCESS
    att2 = ShiftAttendance(
        id=uuid.uuid4(),
        shift_id=shift_id,
        volunteer_id=v2_id,
        status=AttendanceStatus.CLAIMED,
    )
    db_session.add(att2)
    await db_session.flush()

    # 5. Insert Attendance 3 (capacity: 3/2) -> MUST BE REJECTED BY TRIGGER
    att3 = ShiftAttendance(
        id=uuid.uuid4(),
        shift_id=shift_id,
        volunteer_id=v3_id,
        status=AttendanceStatus.CLAIMED,
    )
    db_session.add(att3)

    with pytest.raises(Exception) as exc_info:
        await db_session.flush()

    err_msg = str(exc_info.value)
    assert "reached maximum capacity" in err_msg or "check_shift_capacity" in err_msg

    await db_session.rollback()


@pytest.mark.asyncio
async def test_volunteer_shift_capacity_service_rejection() -> None:
    """Service level test: joining a full shift raises ConflictError."""
    repo = MagicMock(spec=VolunteerRepository)
    repo._session = MagicMock()
    shift_id = uuid.uuid4()
    shift = VolunteerShift(
        id=shift_id,
        role_name="Feeding",
        start_at=datetime.now(UTC) + timedelta(days=1),
        end_at=datetime.now(UTC) + timedelta(days=1, hours=2),
        capacity=2,
    )
    repo.get_shift_by_id_for_update = AsyncMock(return_value=shift)

    vol_profile = VolunteerProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status=VolunteerStatus.ACTIVE,
    )
    repo.get_profile_by_id = AsyncMock(return_value=vol_profile)
    repo.get_profile_by_user_id = AsyncMock(return_value=vol_profile)
    repo.get_attendance_by_shift_and_volunteer = AsyncMock(return_value=None)

    # 2 existing active attendances
    existing_att1 = ShiftAttendance(
        id=uuid.uuid4(),
        shift_id=shift_id,
        volunteer_id=uuid.uuid4(),
        status=AttendanceStatus.CLAIMED,
    )
    existing_att2 = ShiftAttendance(
        id=uuid.uuid4(),
        shift_id=shift_id,
        volunteer_id=uuid.uuid4(),
        status=AttendanceStatus.CHECKED_IN,
    )
    repo.list_attendance_for_shift = AsyncMock(return_value=[existing_att1, existing_att2])

    service = VolunteerService(repository=repo)
    with pytest.raises(ConflictError, match="maximum volunteer capacity"):
        await service.join_shift(shift_id=shift_id, volunteer_id=vol_profile.user_id)


@pytest.mark.asyncio
async def test_volunteer_shift_capacity_service_allows_cancelled_slots() -> None:
    """Service level test: cancelled attendance frees a slot, allowing join."""
    repo = MagicMock(spec=VolunteerRepository)
    repo._session = MagicMock()
    shift_id = uuid.uuid4()
    shift = VolunteerShift(
        id=shift_id,
        role_name="Feeding",
        start_at=datetime.now(UTC) + timedelta(days=1),
        end_at=datetime.now(UTC) + timedelta(days=1, hours=2),
        capacity=2,
    )
    repo.get_shift_by_id_for_update = AsyncMock(return_value=shift)

    vol_profile = VolunteerProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status=VolunteerStatus.ACTIVE,
    )
    repo.get_profile_by_id = AsyncMock(return_value=vol_profile)
    repo.get_profile_by_user_id = AsyncMock(return_value=vol_profile)
    repo.get_attendance_by_shift_and_volunteer = AsyncMock(return_value=None)

    # 1 claimed + 1 cancelled attendance -> only 1 active, capacity 2 has 1 open slot
    existing_att1 = ShiftAttendance(
        id=uuid.uuid4(),
        shift_id=shift_id,
        volunteer_id=uuid.uuid4(),
        status=AttendanceStatus.CLAIMED,
    )
    existing_cancelled = ShiftAttendance(
        id=uuid.uuid4(),
        shift_id=shift_id,
        volunteer_id=uuid.uuid4(),
        status=AttendanceStatus.CANCELLED,
    )
    repo.list_attendance_for_shift = AsyncMock(return_value=[existing_att1, existing_cancelled])

    created_attendance = ShiftAttendance(
        id=uuid.uuid4(),
        shift_id=shift_id,
        volunteer_id=vol_profile.id,
        status=AttendanceStatus.CLAIMED,
    )
    repo.create_attendance = AsyncMock(return_value=created_attendance)

    service = VolunteerService(repository=repo)
    joined = await service.join_shift(shift_id=shift_id, volunteer_id=vol_profile.user_id)
    assert joined.status == AttendanceStatus.CLAIMED
