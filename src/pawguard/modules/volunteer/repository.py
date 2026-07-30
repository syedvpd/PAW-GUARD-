"""Data access for the Volunteer Management module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting
from pawguard.modules.volunteer.models import (
    ShiftAttendance,
    VolunteerProfile,
    VolunteerShift,
    VolunteerStatus,
)


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

    async def count_profiles(
        self,
        *,
        status: VolunteerStatus | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count(VolunteerProfile.id)).where(VolunteerProfile.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(VolunteerProfile.status == status)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    VolunteerProfile.skills.ilike(like),
                    VolunteerProfile.availability.ilike(like),
                )
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_profiles(
        self,
        *,
        page_params: PageParams | None = None,
        status: VolunteerStatus | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> Sequence[VolunteerProfile]:
        stmt = (
            select(VolunteerProfile)
            .options(selectinload(VolunteerProfile.user))
            .where(VolunteerProfile.deleted_at.is_(None))
        )
        if status is not None:
            stmt = stmt.where(VolunteerProfile.status == status)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    VolunteerProfile.skills.ilike(like),
                    VolunteerProfile.availability.ilike(like),
                )
            )
        valid_sort = {"created_at", "updated_at", "status"}
        if sort:
            stmt = apply_sorting(stmt, sort, valid_sort, default_field="created_at")
        else:
            stmt = stmt.order_by(VolunteerProfile.created_at.desc())
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_shift(self, shift: VolunteerShift) -> VolunteerShift:
        self._session.add(shift)
        await self._session.flush()
        return shift

    async def get_shift_by_id(self, shift_id: uuid.UUID) -> VolunteerShift | None:
        stmt = select(VolunteerShift).where(VolunteerShift.id == shift_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_shifts(self, *, role_name: str | None = None) -> int:
        stmt = select(func.count(VolunteerShift.id))
        if role_name:
            stmt = stmt.where(VolunteerShift.role_name == role_name)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_shifts(
        self,
        *,
        page_params: PageParams | None = None,
        role_name: str | None = None,
        sort: SortParams | None = None,
    ) -> Sequence[VolunteerShift]:
        stmt = select(VolunteerShift)
        if role_name:
            stmt = stmt.where(VolunteerShift.role_name == role_name)
        valid_sort = {"start_at", "end_at", "created_at", "role_name", "capacity"}
        if sort:
            stmt = apply_sorting(stmt, sort, valid_sort, default_field="start_at")
        else:
            stmt = stmt.order_by(VolunteerShift.start_at.asc())
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def create_attendance(self, attendance: ShiftAttendance) -> ShiftAttendance:
        self._session.add(attendance)
        await self._session.flush()
        return attendance

    async def get_attendance_by_id(self, attendance_id: uuid.UUID) -> ShiftAttendance | None:
        stmt = select(ShiftAttendance).where(ShiftAttendance.id == attendance_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_attendance_by_shift_and_volunteer(
        self, shift_id: uuid.UUID, volunteer_id: uuid.UUID
    ) -> ShiftAttendance | None:
        stmt = select(ShiftAttendance).where(
            ShiftAttendance.shift_id == shift_id,
            ShiftAttendance.volunteer_id == volunteer_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_attendance_for_shift(self, shift_id: uuid.UUID) -> int:
        stmt = select(func.count(ShiftAttendance.id)).where(ShiftAttendance.shift_id == shift_id)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_attendance_for_shift(
        self,
        shift_id: uuid.UUID,
        *,
        page_params: PageParams | None = None,
    ) -> Sequence[ShiftAttendance]:
        stmt = (
            select(ShiftAttendance)
            .where(ShiftAttendance.shift_id == shift_id)
            .order_by(ShiftAttendance.created_at.desc())
        )
        if page_params:
            stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def soft_delete_profile(self, profile_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        stmt = (
            select(VolunteerProfile)
            .where(VolunteerProfile.id == profile_id, VolunteerProfile.deleted_at.is_(None))
        )
        profile = (await self._session.execute(stmt)).scalar_one_or_none()
        if profile:
            profile.deleted_at = now

    async def bulk_soft_delete_profiles(self, ids: list[uuid.UUID]) -> int:
        now = datetime.now(UTC)
        stmt = (
            select(VolunteerProfile)
            .where(VolunteerProfile.id.in_(ids), VolunteerProfile.deleted_at.is_(None))
        )
        profiles = (await self._session.execute(stmt)).scalars().all()
        for p in profiles:
            p.deleted_at = now
        return len(profiles)

    async def bulk_update_profile_status(
        self, ids: list[uuid.UUID], status: VolunteerStatus
    ) -> int:
        stmt = (
            select(VolunteerProfile)
            .where(VolunteerProfile.id.in_(ids), VolunteerProfile.deleted_at.is_(None))
        )
        profiles = (await self._session.execute(stmt)).scalars().all()
        for p in profiles:
            p.status = status
        return len(profiles)
