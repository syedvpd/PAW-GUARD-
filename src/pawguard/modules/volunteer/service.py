"""VolunteerService: owns volunteer shifts, attendance, and onboarding logic (RULE-003)."""

import asyncio
import math
import uuid
from datetime import UTC, datetime
from logging import getLogger
from typing import Any

from pawguard.core.config import get_settings
from pawguard.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.pdf_generation import generate_volunteer_certificate
from pawguard.core.responses import PaginationMeta
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType, User
from pawguard.modules.auth.rbac import has_permission
from pawguard.modules.auth.repository import RoleRepository, UserRoleRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.storage.models import FileFolder, StoredFile
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
    VolunteerApplicationResponse,
    VolunteerLifecycleStatus,
    VolunteerProfileCreate,
    VolunteerProfileResponse,
    VolunteerProfileUpdate,
    VolunteerServiceSummary,
    VolunteerShiftCreate,
)
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService

logger = getLogger(__name__)


def calculate_haversine_distance_meters(
    lat1: float, lng1: float, lat2: float, lng2: float
) -> float:
    """Calculate the great-circle distance between two GPS points in meters."""
    r_meters = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_meters * c


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return None
    try:
        from decimal import Decimal

        if isinstance(val, Decimal):
            return float(val)
    except Exception:
        pass
    return None


class VolunteerService:
    def __init__(
        self,
        repository: VolunteerRepository,
        audit_service: AuditService | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service
        self._notification_svc = notification_service
        self._roles = RoleRepository(repository._session)
        self._user_roles = UserRoleRepository(repository._session)

    async def _notify_volunteer(
        self,
        profile: VolunteerProfile,
        *,
        title: str,
        body: str,
        notification_type: str,
        action_url: str | None = None,
    ) -> None:
        if self._notification_svc is None or profile.user is None:
            return
        try:
            from pawguard.modules.notifications.schemas import NotificationSend

            await self._notification_svc.send_notification(
                payload=NotificationSend(
                    user_id=profile.user_id,
                    title=title,
                    body=body,
                    notification_type=notification_type,
                    action_url=action_url,
                    send_email=True,
                    send_push=True,
                ),
                user_email=profile.user.email,
            )
        except Exception as exc:
            logger.warning("Failed to notify volunteer %s: %s", profile.id, exc, exc_info=True)

    async def apply_to_volunteer(
        self,
        user_id: uuid.UUID,
        payload: VolunteerProfileCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> VolunteerApplication:
        # Check if user already has an application
        existing_app = await self._repo.get_application_by_user_id(user_id)
        if existing_app is not None:
            if existing_app.status == ApplicationStatus.REJECTED:
                # Allow reapplication after rejection - update the existing application
                existing_app.status = ApplicationStatus.SUBMITTED
                existing_app.emergency_contact_name = payload.emergency_contact_name
                existing_app.emergency_contact_phone = payload.emergency_contact_phone
                existing_app.skills = payload.skills
                existing_app.availability = payload.availability
                existing_app.notes = payload.notes
                existing_app.medical_conditions = payload.medical_conditions
                existing_app.animal_handling_experience = payload.animal_handling_experience
                existing_app.reviewed_by = None
                existing_app.reviewed_at = None
                existing_app.rejection_reason = None
                await self._repo._session.flush()
                res = await self._repo.get_application_by_id(existing_app.id)
                if res is None:
                    raise NotFoundError("Failed to fetch re-submitted volunteer application.")

                if self._audit:
                    await self._audit.record(
                        event_type=AuthAuditEventType.VOLUNTEER_APPLICATION_SUBMITTED,
                        actor_id=actor_id,
                        ip_address=ip_address or "",
                        user_agent="",
                        metadata={
                            "application_id": str(res.id),
                            "user_id": str(user_id),
                            "action": "reapplication",
                        },
                    )

                await self._notify_volunteer_application(
                    res,
                    title="Volunteer application re-submitted",
                    body=(
                        "Your volunteer application has been re-submitted for review. "
                        "Our coordinator will review your updated application."
                    ),
                    notification_type="volunteer_applied",
                    action_url="/volunteers/my-profile",
                )
                return res
            else:
                raise ConflictError("You have already applied or registered as a volunteer.")

        # Check if user already has a volunteer profile
        existing_profile = await self._repo.get_profile_by_user_id(user_id)
        if existing_profile is not None:
            raise ConflictError("You are already a volunteer.")

        # Create new application
        application = VolunteerApplication(
            user_id=user_id,
            emergency_contact_name=payload.emergency_contact_name,
            emergency_contact_phone=payload.emergency_contact_phone,
            skills=payload.skills,
            availability=payload.availability,
            notes=payload.notes,
            medical_conditions=payload.medical_conditions,
            animal_handling_experience=payload.animal_handling_experience,
            status=ApplicationStatus.SUBMITTED,
        )
        await self._repo.create_application(application)
        res = await self._repo.get_application_by_id(application.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created volunteer application.")

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.VOLUNTEER_APPLICATION_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "application_id": str(res.id),
                    "user_id": str(user_id),
                },
            )

        await self._notify_volunteer_application(
            res,
            title="Volunteer application received",
            body=(
                "Thank you for applying to volunteer with PawGuard. Our "
                "coordinator will review your application and contact you "
                "with the next steps."
            ),
            notification_type="volunteer_applied",
            action_url="/volunteers/my-profile",
        )
        return res

    async def get_application_by_user(self, user_id: uuid.UUID) -> VolunteerApplication | None:
        """Get the volunteer application for a user."""
        return await self._repo.get_application_by_user_id(user_id)

    async def list_applications(
        self,
        *,
        page_params: PageParams | None = None,
        status: ApplicationStatus | None = None,
    ) -> tuple[list[VolunteerApplication], PaginationMeta]:
        """List volunteer applications for the coordinator review queue.

        Applications live in a separate table from approved VolunteerProfile
        rows (see apply_to_volunteer/approve_application) - this is the only
        way for a coordinator to discover application_ids to pass to
        approve_application/reject_application.
        """
        total = await self._repo.count_applications(status=status)
        applications = await self._repo.list_applications(status=status, page_params=page_params)
        meta = build_pagination_meta(total=total, params=page_params or PageParams())
        return list(applications), meta

    async def get_volunteer_lifecycle_status(self, user_id: uuid.UUID) -> VolunteerLifecycleStatus:
        """Get the complete volunteer lifecycle status for a user."""
        application = await self._repo.get_application_by_user_id(user_id)
        profile = await self._repo.get_profile_by_user_id(user_id)

        # Determine lifecycle state
        if profile is not None:
            if profile.status == VolunteerStatus.ACTIVE:
                status = "ACTIVE"
            elif profile.status == VolunteerStatus.INACTIVE:
                status = "INACTIVE"
            elif profile.status == VolunteerStatus.APPLIED:
                status = "PENDING"
            else:
                status = "PENDING"
            can_apply = False
            can_reapply = False
        elif application is not None:
            if application.status == ApplicationStatus.REJECTED:
                status = "REJECTED"
                can_apply = True
                can_reapply = True
            elif application.status in [
                ApplicationStatus.SUBMITTED,
                ApplicationStatus.UNDER_REVIEW,
            ]:
                status = "PENDING"
                can_apply = False
                can_reapply = False
            elif application.status == ApplicationStatus.WITHDRAWN:
                status = "NOT_APPLIED"
                can_apply = True
                can_reapply = True
            else:
                status = "PENDING"
                can_apply = False
                can_reapply = False
        else:
            status = "NOT_APPLIED"
            can_apply = True
            can_reapply = False

        return VolunteerLifecycleStatus(
            status=status,
            application=VolunteerApplicationResponse.model_validate(application)
            if application
            else None,
            profile=VolunteerProfileResponse.model_validate(profile) if profile else None,
            can_apply=can_apply,
            can_reapply=can_reapply,
        )

    async def approve_application(
        self,
        application_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> VolunteerProfile:
        """Approve a volunteer application and create a volunteer profile."""
        application = await self._repo.get_application_by_id(application_id)
        if application is None:
            raise NotFoundError("Volunteer application not found.")

        if (
            application.status != ApplicationStatus.SUBMITTED
            and application.status != ApplicationStatus.UNDER_REVIEW
        ):
            raise ValidationFailedError(
                f"Cannot approve application with status '{application.status}'."
            )

        # Check if profile already exists
        existing_profile = await self._repo.get_profile_by_user_id(application.user_id)
        if existing_profile is not None:
            raise ConflictError("Volunteer profile already exists for this user.")

        # Update application status
        application.status = ApplicationStatus.APPROVED
        application.reviewed_by = reviewer_id
        application.reviewed_at = datetime.now(UTC)

        # Create volunteer profile from application
        profile = VolunteerProfile(
            user_id=application.user_id,
            application_id=application.id,
            emergency_contact_name=application.emergency_contact_name,
            emergency_contact_phone=application.emergency_contact_phone,
            skills=application.skills,
            availability=application.availability,
            notes=application.notes,
            medical_conditions=application.medical_conditions,
            animal_handling_experience=application.animal_handling_experience,
            status=VolunteerStatus.APPLIED,
        )
        await self._repo.create_profile(profile)
        await self._repo._session.flush()

        res = await self._repo.get_profile_by_id(profile.id)
        if res is None:
            raise NotFoundError("Failed to fetch newly created volunteer profile.")

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.VOLUNTEER_APPLICATION_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "application_id": str(application_id),
                    "profile_id": str(res.id),
                    "user_id": str(application.user_id),
                    "action": "approved",
                },
            )

        # Approval only creates the profile at APPLIED - it does not grant
        # shift-joining access. That happens at a separate activation step
        # (a coordinator sets status=ACTIVE after background_check_completed
        # is true, in update_profile below), so this wording must not claim
        # shifts are available yet.
        await self._notify_volunteer(
            res,
            title="Volunteer application approved!",
            body=(
                "Congratulations! Your volunteer application has been approved. "
                "A coordinator will complete your background check next; "
                "you'll be notified once your account is fully active and you "
                "can sign up for shifts."
            ),
            notification_type="volunteer_approved",
            action_url="/volunteers/my-profile",
        )
        return res

    async def reject_application(
        self,
        application_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        reason: str,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> VolunteerApplication:
        """Reject a volunteer application."""
        application = await self._repo.get_application_by_id(application_id)
        if application is None:
            raise NotFoundError("Volunteer application not found.")

        if (
            application.status != ApplicationStatus.SUBMITTED
            and application.status != ApplicationStatus.UNDER_REVIEW
        ):
            raise ValidationFailedError(
                f"Cannot reject application with status '{application.status}'."
            )

        application.status = ApplicationStatus.REJECTED
        application.reviewed_by = reviewer_id
        application.reviewed_at = datetime.now(UTC)
        application.rejection_reason = reason
        await self._repo._session.flush()

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.VOLUNTEER_APPLICATION_SUBMITTED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "application_id": str(application_id),
                    "user_id": str(application.user_id),
                    "action": "rejected",
                    "reason": reason,
                },
            )

        await self._notify_user(
            application.user_id,
            title="Volunteer application update",
            body=(
                "Thank you for your interest in volunteering with PawGuard. "
                "After careful review, we are unable to approve your application at this time. "
                "You may reapply in the future if your circumstances change."
            ),
            notification_type="volunteer_rejected",
            action_url="/volunteers/my-profile",
        )
        return application

    async def _notify_volunteer_application(
        self,
        application: VolunteerApplication,
        *,
        title: str,
        body: str,
        notification_type: str,
        action_url: str | None = None,
    ) -> None:
        """Send notification to volunteer applicant."""
        if self._notification_svc is None:
            return
        try:
            from pawguard.modules.notifications.schemas import NotificationSend

            await self._notification_svc.send_notification(
                payload=NotificationSend(
                    user_id=application.user_id,
                    title=title,
                    body=body,
                    notification_type=notification_type,
                    action_url=action_url,
                    send_email=False,
                    send_push=True,
                ),
            )
        except Exception:
            logger.warning(
                "Failed to send volunteer application notification for application %s",
                application.id,
                exc_info=True,
            )

    async def _notify_user(
        self,
        user_id: uuid.UUID,
        *,
        title: str,
        body: str,
        notification_type: str,
        action_url: str | None = None,
    ) -> None:
        """Send notification to a user."""
        if self._notification_svc is None:
            return
        try:
            from pawguard.modules.notifications.schemas import NotificationSend

            await self._notification_svc.send_notification(
                payload=NotificationSend(
                    user_id=user_id,
                    title=title,
                    body=body,
                    notification_type=notification_type,
                    action_url=action_url,
                    send_email=False,
                    send_push=True,
                ),
            )
        except Exception:
            logger.warning(
                "Failed to send notification to user %s",
                user_id,
                exc_info=True,
            )

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
            # Workflow 5: a volunteer may only be activated after the
            # background verification step is complete.
            if not profile.background_check_completed:
                raise ValidationFailedError(
                    "Volunteer cannot be activated until the background check is completed."
                )
            role = await self._roles.get_by_name("volunteer")
            if role is not None:
                await self._user_roles.grant_role(profile.user_id, role.id)

        await self._repo._session.flush()
        res = await self._repo.get_profile_by_id(profile_id)
        if res is None:
            raise NotFoundError("Volunteer profile not found after update.")

        if res.status == VolunteerStatus.ACTIVE and not was_active:
            await self._notify_volunteer(
                res,
                title="Welcome to the PawGuard volunteer team!",
                body=(
                    "Congratulations! Your volunteer application has been "
                    "approved. You can now sign up for shifts in the volunteer "
                    "portal."
                ),
                notification_type="volunteer_approved",
                action_url="/volunteers/my-profile",
            )
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
            location_name=payload.location_name,
            latitude=payload.latitude,
            longitude=payload.longitude,
            allowed_radius_meters=payload.allowed_radius_meters,
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
        # A cancelled claim must free its capacity slot back up - otherwise
        # cancelling would permanently waste it instead of letting another
        # volunteer join.
        active_attendances = [a for a in attendances if a.status != AttendanceStatus.CANCELLED]
        if len(active_attendances) >= shift.capacity:
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

    async def _resolve_shift_location(
        self, shift: VolunteerShift
    ) -> tuple[float | None, float | None, int]:
        """Resolve the target GPS coordinates and allowed geofence radius for a shift.

        Returns (latitude, longitude, allowed_radius_meters). If no location is
        configured on either the shift or its linked shelter facility, returns
        (None, None, allowed_radius).
        """
        raw_radius = _to_float(getattr(shift, "allowed_radius_meters", None))
        radius = int(raw_radius) if raw_radius is not None else 500

        shift_lat = _to_float(getattr(shift, "latitude", None))
        shift_lng = _to_float(getattr(shift, "longitude", None))
        if shift_lat is not None and shift_lng is not None:
            return shift_lat, shift_lng, radius

        facility_id = getattr(shift, "shelter_facility_id", None)
        if isinstance(facility_id, uuid.UUID):
            from sqlalchemy import select

            from pawguard.modules.shelter.models import ShelterFacility

            stmt = select(ShelterFacility).where(
                ShelterFacility.id == facility_id,
                ShelterFacility.deleted_at.is_(None),
            )
            facility = (await self._repo._session.execute(stmt)).scalar_one_or_none()
            if facility:
                fac_lat = _to_float(getattr(facility, "latitude", None))
                fac_lng = _to_float(getattr(facility, "longitude", None))
                if fac_lat is not None and fac_lng is not None:
                    return fac_lat, fac_lng, radius

        return None, None, radius

    async def _authorize_attendance_action(
        self, attendance: ShiftAttendance, requesting_user: User
    ) -> bool:
        """Returns True if `requesting_user` is the volunteer this attendance
        belongs to (self-service). Raises ForbiddenError if they're neither
        the owning volunteer nor a coordinator/staff user with
        `volunteer:update`. Unlike the old owner-only check, a staff caller
        without their own volunteer profile is not 404'd here - they simply
        fall through to the permission check.
        """
        own_profile = await self._repo.get_profile_by_user_id(requesting_user.id)
        is_self = own_profile is not None and attendance.volunteer_id == own_profile.id
        if not is_self and not has_permission(requesting_user, "volunteer:update"):
            raise ForbiddenError(
                "You do not have permission to manage this volunteer's attendance."
            )
        return is_self

    async def check_in(
        self,
        attendance_id: uuid.UUID,
        requesting_user: User,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        ip_address: str | None = None,
    ) -> ShiftAttendance:
        attendance = await self._repo.get_attendance_by_id(attendance_id)
        if attendance is None:
            raise NotFoundError("Attendance record not found.")

        is_self = await self._authorize_attendance_action(attendance, requesting_user)

        target_profile = await self._repo.get_profile_by_id(attendance.volunteer_id)
        if target_profile is None:
            raise NotFoundError("Volunteer profile not found.")
        if target_profile.status != VolunteerStatus.ACTIVE:
            raise ForbiddenError("This volunteer is not active and cannot be checked in.")

        if attendance.status != AttendanceStatus.CLAIMED:
            if attendance.check_in_at is not None:
                raise ConflictError("Already checked in for this shift.")
            raise ConflictError(f"Cannot check in from status '{attendance.status}'.")

        # Geofence location validation
        shift = await self._repo.get_shift_by_id(attendance.shift_id)
        if shift is not None:
            target_lat, target_lng, allowed_radius = await self._resolve_shift_location(shift)
            if target_lat is not None and target_lng is not None:
                if latitude is None or longitude is None:
                    raise ValidationFailedError(
                        "Check-in rejected: GPS coordinates (latitude and longitude) are required for check-in at this shift location."
                    )
                distance_m = calculate_haversine_distance_meters(
                    latitude, longitude, target_lat, target_lng
                )
                if distance_m > allowed_radius:
                    raise ValidationFailedError(
                        f"Check-in rejected: You are {round(distance_m)} meters away from the shift location, which exceeds the allowed geofence radius of {allowed_radius} meters."
                    )
                attendance.check_in_lat = latitude
                attendance.check_in_lng = longitude
                attendance.check_in_distance_meters = round(distance_m, 2)
            elif latitude is not None and longitude is not None:
                attendance.check_in_lat = latitude
                attendance.check_in_lng = longitude

        attendance.check_in_at = datetime.now(UTC)
        attendance.status = AttendanceStatus.CHECKED_IN

        await self._record_coordinator_attendance_action(
            attendance, requesting_user, is_self, "check_in", ip_address
        )
        return attendance

    async def check_out(
        self,
        attendance_id: uuid.UUID,
        requesting_user: User,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        ip_address: str | None = None,
    ) -> ShiftAttendance:
        attendance = await self._repo.get_attendance_by_id(attendance_id)
        if attendance is None:
            raise NotFoundError("Attendance record not found.")

        is_self = await self._authorize_attendance_action(attendance, requesting_user)

        if attendance.check_in_at is None:
            raise ConflictError("Must check in before checking out.")

        if attendance.status != AttendanceStatus.CHECKED_IN:
            raise ConflictError("Already checked out for this shift.")

        # Geofence location validation
        shift = await self._repo.get_shift_by_id(attendance.shift_id)
        if shift is not None:
            target_lat, target_lng, allowed_radius = await self._resolve_shift_location(shift)
            if target_lat is not None and target_lng is not None:
                if latitude is None or longitude is None:
                    raise ValidationFailedError(
                        "Check-out rejected: GPS coordinates (latitude and longitude) are required for check-out at this shift location."
                    )
                distance_m = calculate_haversine_distance_meters(
                    latitude, longitude, target_lat, target_lng
                )
                if distance_m > allowed_radius:
                    raise ValidationFailedError(
                        f"Check-out rejected: You are {round(distance_m)} meters away from the shift location, which exceeds the allowed geofence radius of {allowed_radius} meters."
                    )
                attendance.check_out_lat = latitude
                attendance.check_out_lng = longitude
                attendance.check_out_distance_meters = round(distance_m, 2)
            elif latitude is not None and longitude is not None:
                attendance.check_out_lat = latitude
                attendance.check_out_lng = longitude

        now = datetime.now(UTC)
        attendance.check_out_at = now
        attendance.status = AttendanceStatus.CHECKED_OUT

        delta = now - attendance.check_in_at
        attendance.hours_logged = round(delta.total_seconds() / 3600.0, 2)

        await self._record_coordinator_attendance_action(
            attendance, requesting_user, is_self, "check_out", ip_address
        )
        return attendance

    async def mark_no_show(
        self,
        attendance_id: uuid.UUID,
        requesting_user: User,
        reason: str,
        *,
        ip_address: str | None = None,
    ) -> ShiftAttendance:
        """Coordinator-only: a volunteer never marks themself a no-show, and
        it's never inferred merely from a missing check-in - it's an
        explicit coordinator judgment call after the shift.
        """
        if not has_permission(requesting_user, "volunteer:update"):
            raise ForbiddenError("You do not have permission to mark a volunteer as a no-show.")

        attendance = await self._repo.get_attendance_by_id(attendance_id)
        if attendance is None:
            raise NotFoundError("Attendance record not found.")

        if attendance.status != AttendanceStatus.CLAIMED:
            raise ConflictError(
                f"Cannot mark as no-show from status '{attendance.status}'; "
                "only a claimed-but-not-checked-in attendance can be a no-show."
            )

        attendance.status = AttendanceStatus.NO_SHOW
        attendance.no_show_reason = reason
        attendance.no_show_marked_by = requesting_user.id
        attendance.no_show_marked_at = datetime.now(UTC)

        if self._audit:
            await self._audit.record(
                event_type=AuthAuditEventType.VOLUNTEER_ATTENDANCE_UPDATED,
                actor_id=requesting_user.id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "attendance_id": str(attendance_id),
                    "volunteer_id": str(attendance.volunteer_id),
                    "action": "no_show",
                },
            )
        return attendance

    async def cancel_attendance(
        self,
        attendance_id: uuid.UUID,
        requesting_user: User,
        reason: str | None = None,
        *,
        ip_address: str | None = None,
    ) -> ShiftAttendance:
        attendance = await self._repo.get_attendance_by_id(attendance_id)
        if attendance is None:
            raise NotFoundError("Attendance record not found.")

        is_self = await self._authorize_attendance_action(attendance, requesting_user)

        if attendance.status != AttendanceStatus.CLAIMED:
            raise ConflictError(
                f"Cannot cancel from status '{attendance.status}'; only a "
                "claimed-but-not-started attendance can be cancelled."
            )

        attendance.status = AttendanceStatus.CANCELLED
        attendance.cancelled_reason = reason
        attendance.cancelled_by = requesting_user.id
        attendance.cancelled_at = datetime.now(UTC)

        await self._record_coordinator_attendance_action(
            attendance, requesting_user, is_self, "cancel", ip_address
        )
        return attendance

    async def _record_coordinator_attendance_action(
        self,
        attendance: ShiftAttendance,
        requesting_user: User,
        is_self: bool,
        action: str,
        ip_address: str | None,
    ) -> None:
        """Self-service check-in/out/cancel is routine and already covered
        by request logging; only a coordinator/staff action taken on
        someone else's attendance gets its own audit record.
        """
        if is_self or self._audit is None:
            return
        await self._audit.record(
            event_type=AuthAuditEventType.VOLUNTEER_ATTENDANCE_UPDATED,
            actor_id=requesting_user.id,
            ip_address=ip_address or "",
            user_agent="",
            metadata={
                "attendance_id": str(attendance.id),
                "volunteer_id": str(attendance.volunteer_id),
                "action": action,
            },
        )

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

    async def list_all_attendance_for_volunteer(
        self, volunteer_id: uuid.UUID
    ) -> list[ShiftAttendance]:
        return list(await self._repo.list_all_attendance_for_volunteer(volunteer_id))

    # --- Service certificates (PRR 3.9) ------------------------------------

    async def get_service_summary(self, profile_id: uuid.UUID) -> VolunteerServiceSummary:
        """Aggregate a volunteer's verified service hours from completed
        (checked-out) attendance records."""
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Volunteer profile not found.")

        records = await self._repo.list_attendance_for_volunteer(profile_id)
        total_hours = sum(float(r.hours_logged) for r in records if r.hours_logged is not None)
        period_start = records[0].check_out_at if records else None
        period_end = records[-1].check_out_at if records else None
        roles = sorted(
            {r.shift.role_name for r in records if r.shift is not None and r.shift.role_name}
        )
        return VolunteerServiceSummary(
            volunteer_id=profile_id,
            total_hours=round(total_hours, 2),
            shifts_count=len(records),
            period_start=period_start,
            period_end=period_end,
            role_summary=", ".join(roles),
        )

    async def issue_service_certificate(
        self,
        profile_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        storage_service: StorageService | None = None,
    ) -> tuple[bytes, str]:
        """Generate and store a PDF service certificate for a volunteer based
        on verified attended shifts. Returns (pdf_bytes, object_key)."""
        profile = await self._repo.get_profile_by_id(profile_id)
        if profile is None:
            raise NotFoundError("Volunteer profile not found.")

        summary = await self.get_service_summary(profile_id)
        if summary.shifts_count == 0:
            raise ValidationFailedError(
                "No verified shifts to certify; the volunteer must complete at "
                "least one attended shift first."
            )

        volunteer_name = profile.user.full_name if profile.user else "Volunteer"
        settings = get_settings()
        pdf_bytes = await asyncio.to_thread(
            generate_volunteer_certificate,
            volunteer_name=volunteer_name,
            total_hours=summary.total_hours,
            shifts_count=summary.shifts_count,
            period_start=summary.period_start,
            period_end=summary.period_end,
            role_summary=summary.role_summary,
            org_name=settings.org_name,
            org_address=settings.org_address,
            issued_at=datetime.now(UTC),
        )

        if storage_service is not None:
            object_key = storage_service.build_object_key(
                folder=FileFolder.CERTIFICATES.value,
                filename=f"service_certificate_{profile_id}.pdf",
            )
            await asyncio.to_thread(
                storage_service.put_object,
                object_key=object_key,
                content=pdf_bytes,
                content_type="application/pdf",
            )
            stored = StoredFile(
                object_key=object_key,
                original_filename=f"service_certificate_{profile_id}.pdf",
                mime_type="application/pdf",
                file_size=len(pdf_bytes),
                folder=FileFolder.CERTIFICATES.value,
                is_uploaded=True,
                uploaded_at=datetime.now(UTC),
                entity_type="volunteer_certificate",
                entity_id=profile_id,
                user_id=profile.user_id,
            )
            self._repo._session.add(stored)
            await self._repo._session.flush()
        else:
            object_key = ""

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.VOLUNTEER_CERTIFICATE_ISSUED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "profile_id": str(profile_id),
                    "volunteer_id": str(profile.user_id),
                    "total_hours": str(summary.total_hours),
                    "shifts_count": summary.shifts_count,
                    "object_key": object_key,
                },
            )
        return pdf_bytes, object_key
