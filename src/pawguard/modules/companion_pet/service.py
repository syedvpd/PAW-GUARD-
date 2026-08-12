"""Business services for companion pets and veterinary workflows."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.dependencies import CurrentUser
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.auth.rbac import is_admin_role
from pawguard.modules.companion_pet.models import (
    AppointmentStatus,
    ClinicMembership,
    CompanionPet,
    PetAppointment,
    PetClinicAccess,
    PetMedicalRecord,
    PetReminder,
    ReminderDelivery,
    ReminderKind,
    SafetyTag,
    VetClinic,
)
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.schemas import (
    CompanionPetCreate,
    CompanionPetResponse,
    CompanionPetUpdate,
    MedicalRecordCreate,
    PetAppointmentCreate,
    PetAppointmentResponse,
    PetReminderCreate,
    VetClinicCreate,
    VetClinicResponse,
    VetClinicUpdate,
    VeterinarianResponse,
)
from pawguard.modules.notifications.schemas import NotificationCreate
from pawguard.modules.notifications.service import NotificationService
from pawguard.modules.storage.models import FileFolder, StoredFile
from pawguard.modules.storage.schemas import StoredFileCreate, StoredFileResponse, UploadUrlResponse
from pawguard.modules.storage.service import StorageService
from pawguard.services.audit_service import AuditService


def _hash_tag_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _new_tag_token() -> str:
    return secrets.token_urlsafe(32)


class CompanionPetService:
    def __init__(
        self,
        repository: CompanionPetRepository,
        session: AsyncSession,
        *,
        storage: StorageService | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._session = session
        self._storage = storage
        self._audit = audit

    @staticmethod
    def _is_admin(current_user: CurrentUser) -> bool:
        return is_admin_role(current_user.claims)

    async def _get_pet(self, pet_id: uuid.UUID) -> CompanionPet:
        pet = await self._repo.get_pet(pet_id)
        if pet is None:
            raise NotFoundError("Companion pet not found.")
        return pet

    async def _authorize_pet(
        self,
        current_user: CurrentUser,
        pet: CompanionPet,
        *,
        clinic_id: uuid.UUID | None = None,
        owner_only: bool = False,
    ) -> None:
        if self._is_admin(current_user) or pet.owner_id == current_user.id:
            return
        if owner_only:
            raise ForbiddenError("Only the pet owner or an administrator may perform this action.")
        if await self._repo.has_pet_clinic_access(current_user.id, pet.id) and (
            clinic_id is None or await self._repo.has_membership(current_user.id, clinic_id)
        ):
            return
        raise ForbiddenError("You are not authorized for this companion pet record.")

    async def _audit_event(
        self,
        event_type: AuthAuditEventType,
        actor_id: uuid.UUID | None,
        ip_address: str | None,
        metadata: dict[str, object],
    ) -> None:
        if self._audit is not None:
            await self._audit.record(
                event_type=event_type,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata=metadata,
            )

    async def create_pet(
        self, payload: CompanionPetCreate, current_user: CurrentUser, ip_address: str | None = None
    ) -> CompanionPet:
        pet = await self._repo.create_pet(
            CompanionPet(owner_id=current_user.id, **payload.model_dump())
        )
        await self._audit_event(
            AuthAuditEventType.COMPANION_PET_CREATED,
            current_user.id,
            ip_address,
            {"pet_id": pet.id},
        )
        return pet

    async def list_pets(
        self, page: PageParams, sort: SortParams, current_user: CurrentUser
    ) -> PaginatedResponse[CompanionPetResponse]:
        owner_id = None if self._is_admin(current_user) else current_user.id
        rows, total = await self._repo.list_pets(page, sort, owner_id=owner_id)
        return PaginatedResponse(
            data=[CompanionPetResponse.model_validate(row) for row in rows],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def get_pet(self, pet_id: uuid.UUID, current_user: CurrentUser) -> CompanionPet:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        return pet

    async def update_pet(
        self,
        pet_id: uuid.UUID,
        payload: CompanionPetUpdate,
        current_user: CurrentUser,
        ip_address: str | None = None,
    ) -> CompanionPet:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(pet, key, value)
        await self._session.flush()
        await self._session.refresh(pet)
        await self._audit_event(
            AuthAuditEventType.COMPANION_PET_UPDATED,
            current_user.id,
            ip_address,
            {"pet_id": pet.id},
        )
        return pet

    async def delete_pet(
        self, pet_id: uuid.UUID, current_user: CurrentUser, ip_address: str | None = None
    ) -> None:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet, owner_only=True)
        pet.deleted_at = datetime.now(UTC)
        await self._session.flush()
        await self._audit_event(
            AuthAuditEventType.COMPANION_PET_DELETED,
            current_user.id,
            ip_address,
            {"pet_id": pet.id},
        )

    async def create_medical_record(
        self,
        pet_id: uuid.UUID,
        payload: MedicalRecordCreate,
        current_user: CurrentUser,
        ip_address: str | None = None,
    ) -> PetMedicalRecord:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet, clinic_id=payload.clinic_id)
        if payload.clinic_id is not None and await self._repo.get_clinic(payload.clinic_id) is None:
            raise NotFoundError("Veterinary clinic not found.")
        if (
            payload.clinic_id is not None
            and not self._is_admin(current_user)
            and pet.owner_id != current_user.id
            and not await self._repo.has_membership(current_user.id, payload.clinic_id)
        ):
            raise ForbiddenError("You are not a member of the selected veterinary clinic.")
        if payload.stored_file_id is not None:
            if self._storage is None:
                raise ConflictError("Storage service is not configured.")
            stored = await self._storage.get_file(payload.stored_file_id)
            if stored.entity_type != "companion_pet" or stored.entity_id != pet.id:
                raise ForbiddenError("The uploaded file is not owned by this pet record.")
        record = PetMedicalRecord(
            pet_id=pet.id,
            clinic_id=payload.clinic_id,
            authored_by_id=current_user.id,
            stored_file_id=payload.stored_file_id,
            record_type=payload.record_type,
            title=payload.title,
            notes=payload.notes,
            occurred_at=payload.occurred_at or datetime.now(UTC),
        )
        record = await self._repo.create_medical_record(record)
        await self._audit_event(
            AuthAuditEventType.COMPANION_MEDICAL_RECORD_CREATED,
            current_user.id,
            ip_address,
            {"pet_id": pet.id, "record_id": record.id},
        )

        # Auto-create a reminder when next_reminder_at is provided
        if payload.next_reminder_at is not None:
            reminder_kind = payload.reminder_kind or ReminderKind.VACCINATION
            reminder = PetReminder(
                owner_id=pet.owner_id,
                pet_id=pet.id,
                kind=reminder_kind,
                title=f"{reminder_kind.value.title()}: {payload.title}",
                details=payload.notes or f"Reminder for {payload.record_type} record.",
                due_at=payload.next_reminder_at,
                source_key=f"medical_record:{record.id}:{reminder_kind.value}",
            )
            try:
                await self._repo.create_reminder(reminder)
            except IntegrityError:
                await self._session.rollback()

        return record

    async def delete_medical_record(
        self,
        record_id: uuid.UUID,
        current_user: CurrentUser,
        ip_address: str | None = None,
    ) -> None:
        record = await self._repo.get_medical_record(record_id)
        if record is None:
            raise NotFoundError("Medical record not found.")
        pet = await self._get_pet(record.pet_id)
        await self._authorize_pet(current_user, pet, clinic_id=record.clinic_id)
        record.deleted_at = datetime.now(UTC)
        await self._session.flush()
        await self._audit_event(
            AuthAuditEventType.COMPANION_MEDICAL_RECORD_DELETED,
            current_user.id,
            ip_address,
            {"pet_id": pet.id, "record_id": record.id},
        )

    async def list_medical_records(
        self, pet_id: uuid.UUID, current_user: CurrentUser
    ) -> list[PetMedicalRecord]:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        return list(await self._repo.list_medical_records(pet.id))

    async def request_medical_upload(
        self,
        pet_id: uuid.UUID,
        *,
        original_filename: str,
        mime_type: str,
        file_size: int,
        current_user: CurrentUser,
    ) -> UploadUrlResponse:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        if self._storage is None:
            raise ConflictError("Storage service is not configured.")
        payload = StoredFileCreate(
            original_filename=original_filename,
            mime_type=mime_type,
            file_size=file_size,
            folder=FileFolder.MEDICAL,
            entity_type="companion_pet",
            entity_id=pet.id,
        )
        return await self._storage.request_upload_url(payload, user_id=current_user.id)

    async def confirm_medical_upload(
        self, pet_id: uuid.UUID, file_id: uuid.UUID, current_user: CurrentUser
    ) -> StoredFile:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        if self._storage is None:
            raise ConflictError("Storage service is not configured.")
        stored = await self._storage.get_file(file_id)
        if stored.entity_type != "companion_pet" or stored.entity_id != pet.id:
            raise ForbiddenError("You are not authorized for this uploaded file.")
        return await self._storage.confirm_upload(file_id)

    async def list_medical_files(
        self, pet_id: uuid.UUID, page: PageParams, sort: SortParams, current_user: CurrentUser
    ) -> PaginatedResponse[StoredFileResponse]:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        if self._storage is None:
            raise ConflictError("Storage service is not configured.")
        return await self._storage.list_by_entity(
            "companion_pet", pet.id, page, sort, folder=FileFolder.MEDICAL.value
        )

    async def provision_safety_tag(
        self, pet_id: uuid.UUID, current_user: CurrentUser, ip_address: str | None = None
    ) -> tuple[SafetyTag, str]:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet, owner_only=True)
        raw_token = _new_tag_token()
        tag = await self._repo.get_active_tag_for_pet(pet.id)
        if tag is None:
            tag = await self._repo.create_tag(
                SafetyTag(
                    pet_id=pet.id,
                    token_hash=_hash_tag_token(raw_token),
                    token_prefix=raw_token[:8],
                )
            )
        else:
            tag.token_hash = _hash_tag_token(raw_token)
            tag.token_prefix = raw_token[:8]
            tag.is_active = True
            await self._session.flush()
            await self._session.refresh(tag)
        await self._audit_event(
            AuthAuditEventType.SAFETY_TAG_PROVISIONED,
            current_user.id,
            ip_address,
            {"pet_id": pet.id, "tag_id": tag.id},
        )
        return tag, raw_token

    async def scan_safety_tag(
        self, raw_token: str, ip_address: str | None = None
    ) -> tuple[SafetyTag, CompanionPet]:
        tag = await self._repo.get_tag_by_hash(_hash_tag_token(raw_token))
        if tag is None:
            raise NotFoundError("Safety tag not found.")
        pet = await self._get_pet(tag.pet_id)
        if not pet.is_scan_enabled:
            raise NotFoundError("Safety tag not found.")
        tag.last_scanned_at = datetime.now(UTC)
        tag.scan_count = (tag.scan_count or 0) + 1
        await self._session.flush()
        await self._audit_event(
            AuthAuditEventType.SAFETY_TAG_SCANNED,
            None,
            ip_address,
            {"pet_id": pet.id, "tag_id": tag.id},
        )
        return tag, pet

    async def get_pet_photo_url(self, pet_id: uuid.UUID) -> str | None:
        """Return the first uploaded photo URL for a companion pet, or None."""
        if self._storage is None:
            return None
        from sqlalchemy import select

        from pawguard.modules.storage.models import StoredFile

        stmt = (
            select(StoredFile)
            .where(
                StoredFile.deleted_at.is_(None),
                StoredFile.entity_type == "companion_pet",
                StoredFile.entity_id == pet_id,
                StoredFile.is_uploaded.is_(True),
                StoredFile.mime_type.like("image/%"),
            )
            .order_by(StoredFile.created_at.desc())
            .limit(1)
        )
        result = await self._storage._repo._session.execute(stmt)
        stored = result.scalar_one_or_none()
        if stored is None:
            return None
        return await self._storage.get_download_url_for_object(stored.object_key)

    async def get_safety_tag(
        self, pet_id: uuid.UUID, current_user: CurrentUser
    ) -> SafetyTag | None:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        return await self._repo.get_active_tag_for_pet(pet.id)

    async def create_clinic(
        self, payload: VetClinicCreate, current_user: CurrentUser, ip_address: str | None = None
    ) -> VetClinic:
        if not self._is_admin(current_user):
            raise ForbiddenError("Only an administrator may manage veterinary clinics.")
        clinic = await self._repo.create_clinic(VetClinic(**payload.model_dump()))
        await self._audit_event(
            AuthAuditEventType.VET_CLINIC_CREATED,
            current_user.id,
            ip_address,
            {"clinic_id": clinic.id},
        )
        return clinic

    async def list_clinics(
        self, page: PageParams, sort: SortParams, search: str | None = None
    ) -> PaginatedResponse[VetClinicResponse]:
        rows, total = await self._repo.list_clinics(page, sort, search)
        return PaginatedResponse(
            data=[VetClinicResponse.model_validate(row) for row in rows],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def list_clinic_veterinarians(
        self, clinic_id: uuid.UUID
    ) -> list[VeterinarianResponse]:
        if await self._repo.get_clinic(clinic_id) is None:
            raise NotFoundError("Veterinary clinic not found.")
        vets = await self._repo.list_clinic_veterinarians(clinic_id)
        return [VeterinarianResponse.model_validate(v) for v in vets]

    async def update_clinic(
        self,
        clinic_id: uuid.UUID,
        payload: VetClinicUpdate,
        current_user: CurrentUser,
        ip_address: str | None = None,
    ) -> VetClinic:
        if not self._is_admin(current_user):
            raise ForbiddenError("Only an administrator may manage veterinary clinics.")
        clinic = await self._repo.get_clinic(clinic_id)
        if clinic is None:
            raise NotFoundError("Veterinary clinic not found.")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(clinic, key, value)
        await self._session.flush()
        await self._session.refresh(clinic)
        await self._audit_event(
            AuthAuditEventType.VET_CLINIC_UPDATED,
            current_user.id,
            ip_address,
            {"clinic_id": clinic.id},
        )
        return clinic

    async def delete_clinic(
        self, clinic_id: uuid.UUID, current_user: CurrentUser, ip_address: str | None = None
    ) -> None:
        if not self._is_admin(current_user):
            raise ForbiddenError("Only an administrator may manage veterinary clinics.")
        clinic = await self._repo.get_clinic(clinic_id)
        if clinic is None:
            raise NotFoundError("Veterinary clinic not found.")
        clinic.deleted_at = datetime.now(UTC)
        clinic.is_active = False
        await self._session.flush()
        await self._audit_event(
            AuthAuditEventType.VET_CLINIC_DELETED,
            current_user.id,
            ip_address,
            {"clinic_id": clinic.id},
        )

    async def add_membership(
        self,
        clinic_id: uuid.UUID,
        membership_role: str,
        user_id: uuid.UUID,
        current_user: CurrentUser,
    ) -> ClinicMembership:
        if not self._is_admin(current_user):
            raise ForbiddenError("Only an administrator may manage clinic memberships.")
        if await self._repo.get_clinic(clinic_id) is None:
            raise NotFoundError("Veterinary clinic not found.")
        return await self._repo.create_membership(
            ClinicMembership(clinic_id=clinic_id, user_id=user_id, membership_role=membership_role)
        )

    async def create_appointment(
        self,
        payload: PetAppointmentCreate,
        current_user: CurrentUser,
        ip_address: str | None = None,
    ) -> PetAppointment:
        pet = await self._get_pet(payload.pet_id)
        if not self._is_admin(current_user) and pet.owner_id != current_user.id:
            raise ForbiddenError("Only the pet owner or an administrator may book an appointment.")
        if await self._repo.get_clinic(payload.clinic_id) is None:
            raise NotFoundError("Veterinary clinic not found.")
        if payload.vet_id is not None and not await self._repo.has_membership(
            payload.vet_id, payload.clinic_id
        ):
            raise ForbiddenError("The selected veterinarian is not a member of this clinic.")
        if (
            await self._repo.find_appointment_conflict(
                payload.clinic_id, payload.starts_at, payload.ends_at
            )
            is not None
        ):
            raise ConflictError(
                "The veterinary clinic already has an appointment in that time range."
            )
        appointment = PetAppointment(
            owner_id=pet.owner_id,
            status=AppointmentStatus.REQUESTED,
            **payload.model_dump(),
        )
        try:
            appointment = await self._repo.create_appointment(appointment)
            access = await self._repo.get_pet_clinic_access(pet.id, payload.clinic_id)
            if access is None:
                await self._repo.grant_pet_clinic_access(
                    PetClinicAccess(
                        pet_id=pet.id,
                        clinic_id=payload.clinic_id,
                        granted_by_id=current_user.id,
                    )
                )
            elif not access.is_active:
                access.is_active = True
                await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "The veterinary clinic already has an appointment in that time range."
            ) from exc
        await self._audit_event(
            AuthAuditEventType.PET_APPOINTMENT_CREATED,
            current_user.id,
            ip_address,
            {"appointment_id": appointment.id, "pet_id": pet.id},
        )
        return appointment

    async def get_appointment(
        self, appointment_id: uuid.UUID, current_user: CurrentUser
    ) -> PetAppointment:
        appointment = await self._repo.get_appointment(appointment_id)
        if appointment is None:
            raise NotFoundError("Appointment not found.")
        if self._is_admin(current_user) or appointment.owner_id == current_user.id:
            return appointment
        if await self._repo.has_membership(current_user.id, appointment.clinic_id):
            return appointment
        raise ForbiddenError("You are not authorized to access this appointment.")

    async def list_appointments(
        self,
        page: PageParams,
        sort: SortParams,
        current_user: CurrentUser,
        clinic_id: uuid.UUID | None = None,
        pet_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[PetAppointmentResponse]:
        owner_id = None
        if not self._is_admin(current_user):
            if clinic_id is not None and await self._repo.has_membership(
                current_user.id, clinic_id
            ):
                pass
            elif pet_id is not None:
                pet = await self._get_pet(pet_id)
                await self._authorize_pet(current_user, pet)
                owner_id = current_user.id if pet.owner_id == current_user.id else None
            else:
                owner_id = current_user.id
        rows, total = await self._repo.list_appointments(
            page, sort, owner_id=owner_id, clinic_id=clinic_id, pet_id=pet_id
        )
        return PaginatedResponse(
            data=[PetAppointmentResponse.model_validate(row) for row in rows],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def cancel_appointment(
        self,
        appointment_id: uuid.UUID,
        reason: str | None,
        current_user: CurrentUser,
        ip_address: str | None = None,
    ) -> PetAppointment:
        appointment = await self.get_appointment(appointment_id, current_user)
        if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
            raise ConflictError("This appointment can no longer be cancelled.")
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancellation_reason = reason
        await self._session.flush()
        await self._audit_event(
            AuthAuditEventType.PET_APPOINTMENT_CANCELLED,
            current_user.id,
            ip_address,
            {"appointment_id": appointment.id},
        )
        return appointment

    async def update_appointment_status(
        self,
        appointment_id: uuid.UUID,
        status: AppointmentStatus,
        current_user: CurrentUser,
        ip_address: str | None = None,
    ) -> PetAppointment:
        appointment = await self.get_appointment(appointment_id, current_user)
        if not self._is_admin(current_user) and not await self._repo.has_membership(
            current_user.id, appointment.clinic_id
        ):
            raise ForbiddenError("Only clinic staff may confirm or complete appointments.")
        if appointment.status == AppointmentStatus.CANCELLED:
            raise ConflictError("A cancelled appointment cannot be confirmed.")
        appointment.status = status
        await self._session.flush()
        await self._audit_event(
            AuthAuditEventType.PET_APPOINTMENT_STATUS_CHANGED,
            current_user.id,
            ip_address,
            {"appointment_id": appointment.id, "status": status.value},
        )
        return appointment

    async def create_reminder(
        self, pet_id: uuid.UUID, payload: PetReminderCreate, current_user: CurrentUser
    ) -> PetReminder:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        reminder = PetReminder(owner_id=pet.owner_id, pet_id=pet.id, **payload.model_dump())
        try:
            return await self._repo.create_reminder(reminder)
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("A reminder with this source key already exists.") from exc

    async def list_reminders(
        self, pet_id: uuid.UUID, current_user: CurrentUser
    ) -> list[PetReminder]:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        return list(await self._repo.list_reminders(pet.id))

    async def delete_reminder(
        self,
        pet_id: uuid.UUID,
        reminder_id: uuid.UUID,
        current_user: CurrentUser,
    ) -> None:
        pet = await self._get_pet(pet_id)
        await self._authorize_pet(current_user, pet)
        reminder = await self._repo.get_reminder(reminder_id)
        if reminder is None or reminder.pet_id != pet.id:
            raise NotFoundError("Reminder not found.")
        reminder.deleted_at = datetime.now(UTC)
        reminder.is_active = False
        await self._session.flush()


async def deliver_reminder_once(
    repository: CompanionPetRepository,
    notification_service: NotificationService,
    reminder: PetReminder,
) -> bool:
    """Create one in-app reminder delivery; the unique row makes retries safe.

    Also sends a push notification via FCM when the owner has push
    notifications enabled and a valid FCM token is registered.
    """
    scheduled_for = reminder.due_at.replace(microsecond=0)
    if await repository.get_delivery(reminder.id, reminder.owner_id, scheduled_for) is not None:
        return False
    try:
        await repository.create_delivery(
            ReminderDelivery(
                reminder_id=reminder.id,
                user_id=reminder.owner_id,
                scheduled_for=scheduled_for,
                delivered_at=datetime.now(UTC),
            )
        )
        await notification_service.create_notification(
            NotificationCreate(
                user_id=reminder.owner_id,
                title=reminder.title,
                body=reminder.details or f"Reminder due for companion pet {reminder.pet_id}.",
                notification_type=f"companion_pet_{reminder.kind}",
                action_url=f"/api/v1/companion-pets/{reminder.pet_id}/reminders",
            )
        )

        # Push notification via FCM
        await notification_service._send_push_to_users(
            [reminder.owner_id],
            reminder.title,
            reminder.details or f"Reminder due for companion pet {reminder.pet_id}.",
            f"/api/v1/companion-pets/{reminder.pet_id}/reminders",
        )

        return True
    except IntegrityError:
        await repository._session.rollback()
        return False
