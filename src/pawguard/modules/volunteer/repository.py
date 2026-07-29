"""Data access for the Volunteer Management module. Repositories never contain business decisions (RULE-002)."""

import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.volunteer.models import ShiftAttendance, VolunteerProfile, VolunteerShift, VolunteerStatus


class VolunteerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_profile(self, profile: VolunteerProfile) -> VolunteerProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_profile_by_id(self, profile_id: uuid.UUID) -> VolunteerProfile | None:
        stmt = (
            select(VolunteerProfile)
            .options(selectinload(VolunteerProfile.user))
            .where(VolunteerProfile.id == profile_id, VolunteerProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_profile_by_user_id(self, user_id: uuid.UUID) -> VolunteerProfile | None:
        stmt = (
            select(VolunteerProfile)
            .options(selectinload(VolunteerProfile.user))
            .where(VolunteerProfile.user_id == user_id, VolunteerProfile.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_profiles(self, status: VolunteerStatus | None = None) -> Sequence[VolunteerProfile]:
        stmt = (
            select(VolunteerProfile)
            .options(selectinload(VolunteerProfile.user))
            .where(VolunteerProfile.deleted_at.is_(None))
            .order_by(VolunteerProfile.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(VolunteerProfile.status == status)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_shift(self, shift: VolunteerShift) -> VolunteerShift:
        self._session.add(shift)
        await self._session.flush()
        return shift

    async def get_shift_by_id(self, shift_id: uuid.UUID) -> VolunteerShift | None:
        stmt = select(VolunteerShift).where(VolunteerShift.id == shift_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_shifts(self) -> Sequence[VolunteerShift]:
        stmt = select(VolunteerShift).order_by(VolunteerShift.start_at.asc())
        return (await self._session.execute(stmt)).scalars().all()

    async def create_attendance(self, attendance: ShiftAttendance) -> ShiftAttendance:
        self._session.add(attendance)
        await self._session.flush()
        return attendance

    async def get_attendance_by_id(self, attendance_id: uuid.UUID) -> ShiftAttendance | None:
        stmt = select(ShiftAttendance).where(ShiftAttendance.id == attendance_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_attendance_by_shift_and_volunteer(self, shift_id: uuid.UUID, volunteer_id: uuid.UUID) -> ShiftAttendance | None:
        stmt = select(ShiftAttendance).where(
            ShiftAttendance.shift_id == shift_id,
            ShiftAttendance.volunteer_id == volunteer_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_attendance_for_shift(self, shift_id: uuid.UUID) -> Sequence[ShiftAttendance]:
        stmt = select(ShiftAttendance).where(ShiftAttendance.shift_id == shift_id)
        return (await self._session.execute(stmt)).scalars().all()
