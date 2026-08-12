"""Data access for companion pets. Business decisions remain in the service."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.auth.models import Role, User
from pawguard.modules.companion_pet.models import (
    AppointmentStatus,
    ClinicMembership,
    CompanionPet,
    PetAppointment,
    PetClinicAccess,
    PetMedicalRecord,
    PetReminder,
    ReminderDelivery,
    SafetyTag,
    VetClinic,
)


class CompanionPetRepository:
    PET_SORTABLE_FIELDS = {"created_at", "updated_at", "name", "species", "birth_date"}
    CLINIC_SORTABLE_FIELDS = {"created_at", "updated_at", "name"}
    APPOINTMENT_SORTABLE_FIELDS = {"created_at", "starts_at", "ends_at", "status"}

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pet(self, pet: CompanionPet) -> CompanionPet:
        self._session.add(pet)
        await self._session.flush()
        await self._session.refresh(pet)
        return pet

    async def get_pet(self, pet_id: uuid.UUID) -> CompanionPet | None:
        stmt = select(CompanionPet).where(
            CompanionPet.id == pet_id, CompanionPet.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_pets(
        self, page: PageParams, sort: SortParams, owner_id: uuid.UUID | None = None
    ) -> tuple[Sequence[CompanionPet], int]:
        stmt = select(CompanionPet).where(CompanionPet.deleted_at.is_(None))
        if owner_id is not None:
            stmt = stmt.where(CompanionPet.owner_id == owner_id)
        count = await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        total = count.scalar_one()
        stmt = apply_sorting(stmt, sort, self.PET_SORTABLE_FIELDS, "created_at")
        rows = (
            (await self._session.execute(stmt.offset(page.offset).limit(page.limit)))
            .scalars()
            .all()
        )
        return rows, total

    async def create_medical_record(self, record: PetMedicalRecord) -> PetMedicalRecord:
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def get_medical_record(self, record_id: uuid.UUID) -> PetMedicalRecord | None:
        stmt = select(PetMedicalRecord).where(
            PetMedicalRecord.id == record_id, PetMedicalRecord.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_medical_records(self, pet_id: uuid.UUID) -> Sequence[PetMedicalRecord]:
        stmt = (
            select(PetMedicalRecord)
            .where(PetMedicalRecord.pet_id == pet_id, PetMedicalRecord.deleted_at.is_(None))
            .order_by(PetMedicalRecord.occurred_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_reminder(self, reminder_id: uuid.UUID) -> PetReminder | None:
        stmt = select(PetReminder).where(
            PetReminder.id == reminder_id, PetReminder.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_active_tag_for_pet(self, pet_id: uuid.UUID) -> SafetyTag | None:
        stmt = select(SafetyTag).where(
            SafetyTag.pet_id == pet_id,
            SafetyTag.is_active.is_(True),
            SafetyTag.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_tag_by_hash(self, token_hash: str) -> SafetyTag | None:
        stmt = select(SafetyTag).where(
            SafetyTag.token_hash == token_hash,
            SafetyTag.is_active.is_(True),
            SafetyTag.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_tag(self, tag: SafetyTag) -> SafetyTag:
        self._session.add(tag)
        await self._session.flush()
        await self._session.refresh(tag)
        return tag

    async def create_clinic(self, clinic: VetClinic) -> VetClinic:
        self._session.add(clinic)
        await self._session.flush()
        await self._session.refresh(clinic)
        return clinic

    async def get_clinic(self, clinic_id: uuid.UUID) -> VetClinic | None:
        stmt = select(VetClinic).where(VetClinic.id == clinic_id, VetClinic.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_clinics(
        self, page: PageParams, sort: SortParams, search: str | None = None
    ) -> tuple[Sequence[VetClinic], int]:
        stmt = select(VetClinic).where(
            VetClinic.deleted_at.is_(None), VetClinic.is_active.is_(True)
        )
        search_filter = build_search_filter(VetClinic, search, ("name", "address", "services"))
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        total = (
            await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        stmt = apply_sorting(stmt, sort, self.CLINIC_SORTABLE_FIELDS, "name")
        rows = (
            (await self._session.execute(stmt.offset(page.offset).limit(page.limit)))
            .scalars()
            .all()
        )
        return rows, total

    async def create_membership(self, membership: ClinicMembership) -> ClinicMembership:
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def list_clinic_veterinarians(self, clinic_id: uuid.UUID) -> Sequence[User]:
        stmt = (
            select(User)
            .join(User.roles)
            .join(
                ClinicMembership,
                ClinicMembership.user_id == User.id,
            )
            .where(
                Role.name == "veterinarian",
                ClinicMembership.clinic_id == clinic_id,
                ClinicMembership.is_active.is_(True),
                ClinicMembership.deleted_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(User.full_name)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def has_membership(self, user_id: uuid.UUID, clinic_id: uuid.UUID) -> bool:
        stmt = select(ClinicMembership.id).where(
            ClinicMembership.user_id == user_id,
            ClinicMembership.clinic_id == clinic_id,
            ClinicMembership.is_active.is_(True),
            ClinicMembership.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def has_pet_clinic_access(self, user_id: uuid.UUID, pet_id: uuid.UUID) -> bool:
        stmt = (
            select(PetClinicAccess.id)
            .join(ClinicMembership, ClinicMembership.clinic_id == PetClinicAccess.clinic_id)
            .where(
                PetClinicAccess.pet_id == pet_id,
                PetClinicAccess.is_active.is_(True),
                PetClinicAccess.deleted_at.is_(None),
                ClinicMembership.user_id == user_id,
                ClinicMembership.is_active.is_(True),
                ClinicMembership.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def grant_pet_clinic_access(self, access: PetClinicAccess) -> PetClinicAccess:
        self._session.add(access)
        await self._session.flush()
        return access

    async def get_pet_clinic_access(
        self, pet_id: uuid.UUID, clinic_id: uuid.UUID
    ) -> PetClinicAccess | None:
        stmt = select(PetClinicAccess).where(
            PetClinicAccess.pet_id == pet_id,
            PetClinicAccess.clinic_id == clinic_id,
            PetClinicAccess.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_appointment(self, appointment: PetAppointment) -> PetAppointment:
        self._session.add(appointment)
        await self._session.flush()
        await self._session.refresh(appointment)
        return appointment

    async def get_appointment(self, appointment_id: uuid.UUID) -> PetAppointment | None:
        stmt = select(PetAppointment).where(
            PetAppointment.id == appointment_id, PetAppointment.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_appointment_conflict(
        self, clinic_id: uuid.UUID, starts_at: datetime, ends_at: datetime
    ) -> PetAppointment | None:
        stmt = select(PetAppointment).where(
            PetAppointment.clinic_id == clinic_id,
            PetAppointment.deleted_at.is_(None),
            PetAppointment.status.in_((AppointmentStatus.REQUESTED, AppointmentStatus.CONFIRMED)),
            PetAppointment.starts_at < ends_at,
            PetAppointment.ends_at > starts_at,
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def list_appointments(
        self,
        page: PageParams,
        sort: SortParams,
        *,
        owner_id: uuid.UUID | None = None,
        clinic_id: uuid.UUID | None = None,
        pet_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[PetAppointment], int]:
        stmt = select(PetAppointment).where(PetAppointment.deleted_at.is_(None))
        if owner_id is not None:
            stmt = stmt.where(PetAppointment.owner_id == owner_id)
        if clinic_id is not None:
            stmt = stmt.where(PetAppointment.clinic_id == clinic_id)
        if pet_id is not None:
            stmt = stmt.where(PetAppointment.pet_id == pet_id)
        total = (
            await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        stmt = apply_sorting(stmt, sort, self.APPOINTMENT_SORTABLE_FIELDS, "starts_at")
        rows = (
            (await self._session.execute(stmt.offset(page.offset).limit(page.limit)))
            .scalars()
            .all()
        )
        return rows, total

    async def create_reminder(self, reminder: PetReminder) -> PetReminder:
        self._session.add(reminder)
        await self._session.flush()
        await self._session.refresh(reminder)
        return reminder

    async def list_reminders(self, pet_id: uuid.UUID) -> Sequence[PetReminder]:
        stmt = (
            select(PetReminder)
            .where(
                PetReminder.pet_id == pet_id,
                PetReminder.deleted_at.is_(None),
                PetReminder.is_active.is_(True),
            )
            .order_by(PetReminder.due_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_due_reminders(
        self, from_at: datetime, until: datetime
    ) -> Sequence[PetReminder]:
        """Return active, non-deleted reminders due within [from_at, until]."""
        stmt = select(PetReminder).where(
            PetReminder.deleted_at.is_(None),
            PetReminder.is_active.is_(True),
            PetReminder.due_at >= from_at,
            PetReminder.due_at <= until,
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_delivery(
        self, reminder_id: uuid.UUID, user_id: uuid.UUID, scheduled_for: datetime
    ) -> ReminderDelivery | None:
        stmt = select(ReminderDelivery).where(
            ReminderDelivery.reminder_id == reminder_id,
            ReminderDelivery.user_id == user_id,
            ReminderDelivery.scheduled_for == scheduled_for,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_delivery(self, delivery: ReminderDelivery) -> ReminderDelivery:
        self._session.add(delivery)
        await self._session.flush()
        return delivery
