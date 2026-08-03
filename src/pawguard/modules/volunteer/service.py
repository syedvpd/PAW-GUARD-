"""VolunteerService: owns volunteer shifts, attendance, and onboarding logic (RULE-003)."""

import uuid
from datetime import UTC, datetime

from pawguard.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginationMeta
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.auth.repository import RoleRepository, UserRoleRepository
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
from pawguard.services.audit_service import AuditService


class VolunteerService:
    def __init__(
        self, repository: VolunteerRepository, audit_service: AuditService | None = None
    ) -> None:
        self._repo = repository
        self._audit = audit_service
        self._roles = RoleRepository(repository._session)
        self._user_roles = UserRoleRepository(repository._session)

    async def apply_to_volunteer(
        self,
        user_id: uuid.UUID,
        payload: VolunteerProfileCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
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
            medical_conditions=payload.medical_conditions,
            animal_handling_experience=payload.animal_handling_experience,
            status=VolunteerStatus.APPLIED,
        )
        await self._repo.create_profile(profile)
        res = await self._repo.get_profile_by_id(profile.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created volunteer profile.")

        # Self-service public application - always audited so coordinators can
        # trace who registered, from where, and when (PRR §6.1).
        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.VOLUNTEER_APPLICATION_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "profile_id": str(res.id),
                    "user_id": str(user_id),
                },
            )
        return res

    async def update_profile(
        self, profile_id: uuid.UUID, payload: VolunteerProfileUpdate
    ) -> VolunteerProfile:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Volunteer profile not found.")

        update_data = payload.model_dump(exclude_unset=True)
        was_active = profile.status == VolunteerStatus.ACTIVE
        for key, value in update_data.items():
            setattr(profile, key, value)

        # Coordinator approval is what actually unlocks self-service
        # volunteer access - the "volunteer" role is granted here, not at
        # application time, so an unvetted applicant can't self-escalate.
        if profile.status == VolunteerStatus.ACTIVE and not was_active:
            role = await self._roles.get_by_name("volunteer")
            if role is not None:
                await self._user_roles.grant_role(profile.user_id, role.id)

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

    async def list_profiles(
        self,
        *,
        page_params: PageParams | None = None,
        status: VolunteerStatus | None = None,
        search: str | None = None,
        sort: SortParams | None = None,
    ) -> tuple[list[VolunteerProfile], PaginationMeta]:
        total = await self._repo.count_profiles(status=status, search=search)
        profiles = await self._repo.list_profiles(
            page_params=page_params,
            status=status,
            search=search,
            sort=sort,
        )
        meta = build_pagination_meta(total=total, params=page_params or PageParams())
        return list(profiles), meta

    async def create_shift(self, payload: VolunteerShiftCreate) -> VolunteerShift:
        shift = VolunteerShift(
            shelter_facility_id=payload.shelter_facility_id,
            role_name=payload.role_name,
            start_at=payload.start_at,
            end_at=payload.end_at,
            capacity=payload.capacity,
        )
        return await self._repo.create_shift(shift)

    async def list_shifts(
        self,
        *,
        page_params: PageParams | None = None,
        role_name: str | None = None,
        sort: SortParams | None = None,
    ) -> tuple[list[VolunteerShift], PaginationMeta]:
        total = await self._repo.count_shifts(role_name=role_name)
        shifts = await self._repo.list_shifts(
            page_params=page_params,
            role_name=role_name,
            sort=sort,
        )
        meta = build_pagination_meta(total=total, params=page_params or PageParams())
        return list(shifts), meta

    async def join_shift(self, shift_id: uuid.UUID, volunteer_id: uuid.UUID) -> ShiftAttendance:
        volunteer = await self._repo.get_profile_by_id(volunteer_id)
        if volunteer is None:
            raise NotFoundError("Volunteer profile not found.")
        if volunteer.status != VolunteerStatus.ACTIVE:
            raise ForbiddenError(
                "Your volunteer application must be approved by a coordinator "
                "before you can join shifts."
            )

        # Lock the shift row first: this serializes concurrent joins near
        # capacity so the check-then-act below can't race (mirrors the same
        # fix already applied to kennel assignment and adoption approval).
        shift = await self._repo.get_shift_by_id_for_update(shift_id)
        if shift is None:
            raise NotFoundError("Volunteer shift not found.")

        existing = await self._repo.get_attendance_by_shift_and_volunteer(shift_id, volunteer_id)
        if existing is not None:
            raise ConflictError("You have already joined this shift.")

        attendances = await self._repo.list_attendance_for_shift(shift_id)
        if len(attendances) >= shift.capacity:
            raise ConflictError("This shift has reached its maximum volunteer capacity.")

        attendance = ShiftAttendance(
            shift_id=shift_id,
            volunteer_id=volunteer_id,
        )
        return await self._repo.create_attendance(attendance)

    async def list_attendance(
        self,
        shift_id: uuid.UUID,
        *,
        page_params: PageParams | None = None,
    ) -> tuple[list[ShiftAttendance], PaginationMeta]:
        total = await self._repo.count_attendance_for_shift(shift_id)
        records = await self._repo.list_attendance_for_shift(shift_id, page_params=page_params)
        meta = build_pagination_meta(total=total, params=page_params or PageParams())
        return list(records), meta

    async def check_in(
        self, attendance_id: uuid.UUID, requesting_user_id: uuid.UUID
    ) -> ShiftAttendance:
        attendance = await self._repo.get_attendance_by_id(attendance_id)
        if attendance is None:
            raise NotFoundError("Attendance record not found.")

        profile = await self.get_profile_by_user(requesting_user_id)
        if attendance.volunteer_id != profile.id:
            raise ForbiddenError("You can only check in for your own shifts.")

        if attendance.check_in_at is not None:
            raise ConflictError("Already checked in for this shift.")

        attendance.check_in_at = datetime.now(UTC)
        return attendance

    async def check_out(
        self, attendance_id: uuid.UUID, requesting_user_id: uuid.UUID
    ) -> ShiftAttendance:
        attendance = await self._repo.get_attendance_by_id(attendance_id)
        if attendance is None:
            raise NotFoundError("Attendance record not found.")

        profile = await self.get_profile_by_user(requesting_user_id)
        if attendance.volunteer_id != profile.id:
            raise ForbiddenError("You can only check out of your own shifts.")

        if attendance.check_in_at is None:
            raise ConflictError("Must check in before checking out.")

        if attendance.check_out_at is not None:
            raise ConflictError("Already checked out for this shift.")

        now = datetime.now(UTC)
        attendance.check_out_at = now

        delta = now - attendance.check_in_at
        attendance.hours_logged = round(delta.total_seconds() / 3600.0, 2)
        return attendance

    async def soft_delete_profile(self, profile_id: uuid.UUID) -> None:
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Volunteer profile not found.")
        await self._repo.soft_delete_profile(profile_id)

    async def bulk_delete_profiles(self, ids: list[uuid.UUID]) -> int:
        return await self._repo.bulk_soft_delete_profiles(ids)

    async def bulk_update_profile_status(
        self, ids: list[uuid.UUID], status: VolunteerStatus
    ) -> int:
        return await self._repo.bulk_update_profile_status(ids, status)
