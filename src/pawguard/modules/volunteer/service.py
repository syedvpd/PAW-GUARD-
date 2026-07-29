"""VolunteerService: owns volunteer shifts, attendance, and onboarding logic (RULE-003)."""

import uuid
from datetime import UTC, datetime
from typing import Sequence

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.volunteer.models import ShiftAttendance, VolunteerProfile, VolunteerShift, VolunteerStatus
from pawguard.modules.volunteer.repository import VolunteerRepository
from pawguard.modules.volunteer.schemas import VolunteerProfileCreate, VolunteerProfileUpdate, VolunteerShiftCreate


class VolunteerService:
    def __init__(self, repository: VolunteerRepository) -> None:
        self._repo = repository

    async def apply_to_volunteer(
        self, user_id: uuid.UUID, payload: VolunteerProfileCreate
    ) -> VolunteerProfile:
        existing = await self._repo.get_profile_by_user_id(user_id)
        if existing is not None:
            raise ConflictError("You have already applied or registered as a volunteer.")

        profile = VolunteerProfile(
            user_id=user_id,
            emergency_contact_name=payload.emergency_contact_name,
            emergency_contact_phone=payload.emergency_contact_phone,
            skills=payload.skills,
            availability=payload.availability,
            notes=payload.notes,
            status=VolunteerStatus.APPLIED,
        )
        await self._repo.create_profile(profile)
        res = await self._repo.get_profile_by_id(profile.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created volunteer profile.")
        return res

    async def update_profile(
        self, profile_id: uuid.UUID, payload: VolunteerProfileUpdate
    ) -> VolunteerProfile:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Volunteer profile not found.")

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(profile, key, value)

        await self._repo._session.flush()
        res = await self._repo.get_profile_by_id(profile_id)
        if res is None:
            raise NotFoundError("Volunteer profile not found after update.")
        return res

    async def get_profile(self, profile_id: uuid.UUID) -> VolunteerProfile:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Volunteer profile not found.")
        return profile

    async def get_profile_by_user(self, user_id: uuid.UUID) -> VolunteerProfile:
        profile = await self._repo.get_profile_by_user_id(user_id)
        if profile is None:
            raise NotFoundError("Volunteer profile not found for this user.")
        return profile

    async def list_profiles(self, status: VolunteerStatus | None = None) -> Sequence[VolunteerProfile]:
        return await self._repo.list_profiles(status)

    async def create_shift(self, payload: VolunteerShiftCreate) -> VolunteerShift:
        shift = VolunteerShift(
            shelter_facility_id=payload.shelter_facility_id,
            role_name=payload.role_name,
            start_at=payload.start_at,
            end_at=payload.end_at,
            capacity=payload.capacity,
        )
        return await self._repo.create_shift(shift)

    async def join_shift(self, shift_id: uuid.UUID, volunteer_id: uuid.UUID) -> ShiftAttendance:
        shift = await self._repo.get_shift_by_id(shift_id)
        if shift is None:
            raise NotFoundError("Volunteer shift not found.")

        # Check if already joined
        existing = await self._repo.get_attendance_by_shift_and_volunteer(shift_id, volunteer_id)
        if existing is not None:
            raise ConflictError("You have already joined this shift.")

        # Check capacity
        attendances = await self._repo.list_attendance_for_shift(shift_id)
        if len(attendances) >= shift.capacity:
            raise ConflictError("This shift has reached its maximum volunteer capacity.")

        attendance = ShiftAttendance(
            shift_id=shift_id,
            volunteer_id=volunteer_id,
        )
        return await self._repo.create_attendance(attendance)

    async def check_in(self, attendance_id: uuid.UUID) -> ShiftAttendance:
        attendance = await self._repo.get_attendance_by_id(attendance_id)
        if attendance is None:
            raise NotFoundError("Attendance record not found.")

        if attendance.check_in_at is not None:
            raise ConflictError("Already checked in for this shift.")

        attendance.check_in_at = datetime.now(UTC)
        return attendance

    async def check_out(self, attendance_id: uuid.UUID) -> ShiftAttendance:
        attendance = await self._repo.get_attendance_by_id(attendance_id)
        if attendance is None:
            raise NotFoundError("Attendance record not found.")

        if attendance.check_in_at is None:
            raise ConflictError("Must check in before checking out.")

        if attendance.check_out_at is not None:
            raise ConflictError("Already checked out for this shift.")

        now = datetime.now(UTC)
        attendance.check_out_at = now

        # Calculate logged hours
        delta = now - attendance.check_in_at
        attendance.hours_logged = round(delta.total_seconds() / 3600.0, 2)
        return attendance

    async def list_shifts(self) -> Sequence[VolunteerShift]:
        return await self._repo.list_shifts()
