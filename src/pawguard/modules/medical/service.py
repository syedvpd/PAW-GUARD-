"""MedicalService: owns all medical examinations, surgeries, prescriptions.

(RULE-003) — clearances behaviour.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import OperationalError, ProgrammingError

from pawguard.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from pawguard.core.logging import get_logger
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.inventory.models import MovementType
from pawguard.modules.inventory.schemas import InventoryConsumptionItem, InventoryMovementCreate
from pawguard.modules.inventory.service import InventoryService
from pawguard.modules.medical.models import (
    ClinicalExam,
    MedicalClearance,
    MedicalTreatment,
    MedicationAdministrationLog,
    Prescription,
    VaccinationRecord,
    VaccineProtocol,
)
from pawguard.modules.medical.repository import MedicalRepository
from pawguard.modules.medical.schemas import (
    ClinicalExamCreate,
    ClinicalExamResponse,
    DogMedicalReminderItem,
    DogMedicalRemindersResponse,
    MedicalClearanceCreate,
    MedicalTreatmentCreate,
    MedicalTreatmentResponse,
    MedicationAdministrationCreate,
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionUpdate,
    VaccinationRecordCreate,
    VaccinationRecordResponse,
    VaccineProtocolCreate,
)
from pawguard.services.audit_service import AuditService

logger = get_logger(__name__)


class MedicalService:
    def __init__(
        self,
        repository: MedicalRepository,
        dog_repo: DogRepository,
        audit_service: AuditService | None = None,
        inventory_service: InventoryService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._audit = audit_service
        self._inventory = inventory_service

    async def perform_clinical_exam(
        self,
        vet_id: uuid.UUID,
        payload: ClinicalExamCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ClinicalExam:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        exam = ClinicalExam(
            dog_id=payload.dog_id,
            vet_id=vet_id,
            exam_date=datetime.now(UTC),
            body_condition_score=payload.body_condition_score,
            dental_health=payload.dental_health,
            ocular_aural_notes=payload.ocular_aural_notes,
            coat_condition=payload.coat_condition,
            visible_injuries=payload.visible_injuries,
            triage_diagnosis=payload.triage_diagnosis,
        )
        exam = await self._repo.create_clinical_exam(exam)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"exam_id": str(exam.id), "dog_id": str(payload.dog_id)},
            )
        return exam

    async def record_treatment(
        self,
        vet_id: uuid.UUID,
        payload: MedicalTreatmentCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> MedicalTreatment:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        treatment = MedicalTreatment(
            dog_id=payload.dog_id,
            vet_id=vet_id,
            treatment_date=datetime.now(UTC),
            treatment_type=payload.treatment_type,
            description=payload.description,
            anesthesia_log=payload.anesthesia_log,
            post_op_notes=payload.post_op_notes,
        )
        treatment = await self._repo.create_treatment(treatment)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"treatment_id": str(treatment.id), "dog_id": str(payload.dog_id)},
            )
        await self._record_inventory_consumptions(
            user_id=vet_id,
            consumptions=payload.inventory_consumptions,
            reference_type="medical_treatment",
            reference_id=treatment.id,
            actor_id=actor_id,
            ip_address=ip_address,
        )
        # Workflow 2: while under veterinary treatment the dog is in the clinic.
        dog.status = DogStatus.CLINIC
        await self._repo._session.flush()
        return treatment

    async def administer_vaccine(
        self,
        vet_id: uuid.UUID,
        payload: VaccinationRecordCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> VaccinationRecord:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        rec = VaccinationRecord(
            dog_id=payload.dog_id,
            administered_by=vet_id,
            vaccine_name=payload.vaccine_name,
            administered_at=datetime.now(UTC),
            next_due_at=payload.next_due_at,
            lot_number=payload.lot_number,
        )
        rec = await self._repo.create_vaccination(rec)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.VACCINATION_RECORDED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"vaccination_id": str(rec.id), "dog_id": str(payload.dog_id)},
            )
        await self.schedule_next_dose(rec)
        return rec

    async def schedule_next_dose(self, record: VaccinationRecord) -> VaccinationRecord | None:
        """Auto-create the next protocol-driven vaccination dose (PRR 3.5).

        Looks up the matching ``VaccineProtocol`` by normalized vaccine name.
        When a protocol exists and the administered record has no explicit
        ``next_due_at`` yet, the due date is derived from the protocol interval
        and a placeholder record for the upcoming dose is persisted. The
        protocol table is optional: missing rows (or an unprovisioned table in
        environments without migrations) simply disable auto-scheduling.
        """
        if record.next_due_at is not None:
            return None

        try:
            protocol = await self._repo.get_vaccine_protocol_by_name(record.vaccine_name)
        except (OperationalError, ProgrammingError):
            logger.warning(
                "vaccine_protocol_lookup_unavailable",
                vaccination_id=str(record.id),
                vaccine_name=record.vaccine_name,
            )
            return None
        if protocol is None:
            return None

        next_due = record.administered_at + timedelta(days=protocol.default_interval_days)
        record.next_due_at = next_due
        next_rec = VaccinationRecord(
            dog_id=record.dog_id,
            administered_by=record.administered_by,
            vaccine_name=record.vaccine_name,
            administered_at=next_due,
            next_due_at=None,
            lot_number=None,
        )
        return await self._repo.create_vaccination(next_rec)

    async def prescribe_medication(
        self,
        vet_id: uuid.UUID,
        payload: PrescriptionCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Prescription:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        prescription = Prescription(
            dog_id=payload.dog_id,
            vet_id=vet_id,
            drug_name=payload.drug_name,
            dosage=payload.dosage,
            route=payload.route,
            start_at=payload.start_at,
            end_at=payload.end_at,
            is_active=True,
        )
        prescription = await self._repo.create_prescription(prescription)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"prescription_id": str(prescription.id), "dog_id": str(payload.dog_id)},
            )
        await self._record_inventory_consumptions(
            user_id=vet_id,
            consumptions=payload.inventory_consumptions,
            reference_type="prescription",
            reference_id=prescription.id,
            actor_id=actor_id,
            ip_address=ip_address,
        )
        return prescription

    async def authorize_adoption_clearance(
        self,
        dog_id: uuid.UUID,
        roles: set[str],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        payload: MedicalClearanceCreate | None = None,
    ) -> bool:
        if not ("veterinarian" in roles or "super_admin" in roles or "system:admin" in roles):
            raise ForbiddenError("Adoption medical clearances require a veterinarian's authority.")

        dog = await self._dog_repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        clearance_payload = payload or MedicalClearanceCreate()

        # The dog-level adoptability flags stay in sync with the persisted
        # clearance decision (PRR 3.5): only an approval grants them.
        if clearance_payload.status == "approved":
            dog.is_adoptable = True
            dog.is_quarantine_passed = True
            # Cleared for adoption: the dog returns to the shelter (available
            # for adoption), leaving the clinic state.
            dog.status = DogStatus.SHELTER

        clearance = MedicalClearance(
            dog_id=dog_id,
            authorized_by_id=actor_id,
            clearance_type=clearance_payload.clearance_type,
            status=clearance_payload.status,
            decision_notes=clearance_payload.decision_notes,
            authorized_at=datetime.now(UTC),
            expires_at=clearance_payload.expires_at,
        )
        await self._repo.create_clearance(clearance)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "dog_id": str(dog_id),
                    "clearance_id": str(clearance.id),
                    "status": clearance.status,
                },
            )
        return True

    async def get_clearances_for_dog(self, dog_id: uuid.UUID) -> Sequence[MedicalClearance]:
        return await self._repo.get_clearances_by_dog(dog_id)

    async def log_medication_administration(
        self,
        nurse_id: uuid.UUID,
        payload: MedicationAdministrationCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> MedicationAdministrationLog:
        dog = await self._dog_repo.get_by_id(payload.dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")
        if payload.prescription_id is not None:
            rx = await self._repo.get_prescription_by_id(payload.prescription_id)
            if rx is None:
                raise NotFoundError("Prescription not found.")

        log = MedicationAdministrationLog(
            prescription_id=payload.prescription_id,
            dog_id=payload.dog_id,
            medication_name=payload.medication_name,
            dosage=payload.dosage,
            route=payload.route,
            administered_at=payload.administered_at or datetime.now(UTC),
            administered_by_id=nurse_id,
            notes=payload.notes,
        )
        log = await self._repo.create_administration(log)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"administration_id": str(log.id), "dog_id": str(payload.dog_id)},
            )
        return log

    async def get_administrations_for_prescription(
        self, prescription_id: uuid.UUID
    ) -> Sequence[MedicationAdministrationLog]:
        return await self._repo.get_administrations_by_prescription(prescription_id)

    async def get_administrations_for_dog(
        self, dog_id: uuid.UUID
    ) -> Sequence[MedicationAdministrationLog]:
        return await self._repo.get_administrations_by_dog(dog_id)

    async def create_vaccine_protocol(
        self,
        payload: VaccineProtocolCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> VaccineProtocol:
        existing = await self._repo.get_vaccine_protocol_by_name(payload.name)
        if existing is not None:
            raise ConflictError(f"Vaccine protocol '{payload.name}' already exists.")
        protocol = VaccineProtocol(
            name=payload.name,
            default_interval_days=payload.default_interval_days,
            is_required=payload.is_required,
        )
        protocol = await self._repo.create_vaccine_protocol(protocol)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"vaccine_protocol_id": str(protocol.id), "name": protocol.name},
            )
        return protocol

    async def list_vaccine_protocols(self) -> Sequence[VaccineProtocol]:
        return await self._repo.list_vaccine_protocols()

    async def get_exams_for_dog(self, dog_id: uuid.UUID) -> Sequence[ClinicalExam]:
        return await self._repo.get_exams_by_dog(dog_id)

    async def get_treatments_for_dog(self, dog_id: uuid.UUID) -> Sequence[MedicalTreatment]:
        return await self._repo.get_treatments_by_dog(dog_id)

    async def get_vaccinations_for_dog(self, dog_id: uuid.UUID) -> Sequence[VaccinationRecord]:
        return await self._repo.get_vaccinations_by_dog(dog_id)

    async def get_prescriptions_for_dog(self, dog_id: uuid.UUID) -> Sequence[Prescription]:
        return await self._repo.get_prescriptions_by_dog(dog_id)

    async def list_exams_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        dog_id: uuid.UUID | None = None,
        vet_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[ClinicalExamResponse]:
        results, total = await self._repo.list_exams_paginated(
            page=page,
            sort=sort,
            search_term=search_term,
            dog_id=dog_id,
            vet_id=vet_id,
        )
        return PaginatedResponse(
            data=[ClinicalExamResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def list_treatments_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        dog_id: uuid.UUID | None = None,
        vet_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[MedicalTreatmentResponse]:
        results, total = await self._repo.list_treatments_paginated(
            page=page,
            sort=sort,
            search_term=search_term,
            dog_id=dog_id,
            vet_id=vet_id,
        )
        return PaginatedResponse(
            data=[MedicalTreatmentResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def list_vaccinations_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        dog_id: uuid.UUID | None = None,
        vet_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[VaccinationRecordResponse]:
        results, total = await self._repo.list_vaccinations_paginated(
            page=page,
            sort=sort,
            search_term=search_term,
            dog_id=dog_id,
            vet_id=vet_id,
        )
        return PaginatedResponse(
            data=[VaccinationRecordResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def list_prescriptions_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        dog_id: uuid.UUID | None = None,
        vet_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[PrescriptionResponse]:
        results, total = await self._repo.list_prescriptions_paginated(
            page=page,
            sort=sort,
            search_term=search_term,
            dog_id=dog_id,
            vet_id=vet_id,
        )
        return PaginatedResponse(
            data=[PrescriptionResponse.model_validate(r) for r in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def soft_delete_exam(
        self,
        exam_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        exam = await self._get_exam_by_id(exam_id)
        if exam is None:
            raise NotFoundError("Clinical exam not found.")
        exam.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"exam_id": str(exam_id)},
            )

    async def soft_delete_treatment(
        self,
        treatment_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        treatment = await self._get_treatment_by_id(treatment_id)
        if treatment is None:
            raise NotFoundError("Medical treatment not found.")
        treatment.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"treatment_id": str(treatment_id)},
            )

    async def soft_delete_vaccination(
        self,
        vaccination_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        vaccination = await self._get_vaccination_by_id(vaccination_id)
        if vaccination is None:
            raise NotFoundError("Vaccination record not found.")
        vaccination.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"vaccination_id": str(vaccination_id)},
            )

    async def soft_delete_prescription(
        self,
        prescription_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        prescription = await self._repo.get_prescription_by_id(prescription_id)
        if prescription is None:
            raise NotFoundError("Prescription not found.")
        prescription.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"prescription_id": str(prescription_id)},
            )

    async def update_prescription(
        self,
        p_id: uuid.UUID,
        payload: PrescriptionUpdate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Prescription:
        prescription = await self._repo.get_prescription_by_id(p_id)
        if prescription is None:
            raise NotFoundError("Prescription not found.")
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(prescription, key, value)
        await self._repo._session.flush()
        await self._repo._session.refresh(prescription)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"prescription_id": str(p_id)},
            )
        return prescription

    async def update_prescription_status(
        self,
        p_id: uuid.UUID,
        is_active: bool,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Prescription:
        prescription = await self._repo.get_prescription_by_id(p_id)
        if prescription is None:
            raise NotFoundError("Prescription not found.")
        prescription.is_active = is_active
        await self._repo._session.flush()
        await self._repo._session.refresh(prescription)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"prescription_id": str(p_id), "is_active": is_active},
            )
        return prescription

    async def bulk_update_prescription_status(
        self,
        ids: list[uuid.UUID],
        is_active: bool,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_update_prescription_status(ids, is_active)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "prescription_ids": [str(i) for i in ids],
                    "is_active": is_active,
                    "count": count,
                },
            )
        return count

    async def bulk_soft_delete(
        self,
        ids: list[uuid.UUID],
        entity_type: str,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_soft_delete(entity_type, ids)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"entity_type": entity_type, "ids": [str(i) for i in ids], "count": count},
            )
        return count

    async def _get_exam_by_id(self, exam_id: uuid.UUID) -> ClinicalExam | None:
        from sqlalchemy import select

        stmt = select(ClinicalExam).where(
            ClinicalExam.id == exam_id,
            ClinicalExam.deleted_at.is_(None),
        )
        return (await self._repo._session.execute(stmt)).scalar_one_or_none()

    async def _get_treatment_by_id(self, treatment_id: uuid.UUID) -> MedicalTreatment | None:
        from sqlalchemy import select

        stmt = select(MedicalTreatment).where(
            MedicalTreatment.id == treatment_id,
            MedicalTreatment.deleted_at.is_(None),
        )
        return (await self._repo._session.execute(stmt)).scalar_one_or_none()

    async def _get_vaccination_by_id(self, vaccination_id: uuid.UUID) -> VaccinationRecord | None:
        from sqlalchemy import select

        stmt = select(VaccinationRecord).where(
            VaccinationRecord.id == vaccination_id,
            VaccinationRecord.deleted_at.is_(None),
        )
        return (await self._repo._session.execute(stmt)).scalar_one_or_none()

    async def _record_inventory_consumptions(
        self,
        user_id: uuid.UUID,
        consumptions: list[InventoryConsumptionItem] | None,
        reference_type: str,
        reference_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        ip_address: str | None,
    ) -> None:
        if not self._inventory or not consumptions:
            return
        for item in consumptions:
            await self._inventory.record_movement(
                user_id=user_id,
                payload=InventoryMovementCreate(
                    item_id=item.item_id,
                    movement_type=MovementType.CHECK_OUT,
                    quantity=item.quantity,
                    notes=f"Consumed for {reference_type} {reference_id}",
                    reference_type=reference_type,
                    reference_id=reference_id,
                ),
                actor_id=actor_id,
                ip_address=ip_address,
            )

    async def get_dog_reminders(self, dog_id: uuid.UUID) -> DogMedicalRemindersResponse:
        """Aggregate automated vaccination, medication, and preventative care reminders for a dog."""
        from datetime import date

        dog = await self._dog_repo.get_by_id(dog_id)
        dog_name = dog.name if dog else "Dog"

        today = date.today()
        vaccinations: list[DogMedicalReminderItem] = []
        medications: list[DogMedicalReminderItem] = []
        preventative_care: list[DogMedicalReminderItem] = []

        # 1. Fetch vaccination records
        vax_records = await self._repo.get_vaccinations_by_dog(dog_id)
        for v in vax_records:
            due_raw = getattr(v, "next_due_at", getattr(v, "next_due_date", None))
            due = due_raw.date() if (due_raw is not None and hasattr(due_raw, "date")) else due_raw
            admin_raw = getattr(v, "administered_at", getattr(v, "administered_date", None))
            admin_date = (
                admin_raw.date()
                if (admin_raw is not None and hasattr(admin_raw, "date"))
                else admin_raw
            )
            lot = getattr(v, "lot_number", getattr(v, "batch_number", "N/A"))
            if due is not None:
                days = (due - today).days
                if days < 0:
                    status = "overdue"
                elif days == 0:
                    status = "due_today"
                else:
                    status = "upcoming"
                vaccinations.append(
                    DogMedicalReminderItem(
                        id=f"vax-{v.id}",
                        kind="vaccination",
                        title=f"{v.vaccine_name} Booster",
                        due_date=due,
                        status=status,
                        details=(f"Last administered on {admin_date} (Lot/Batch: {lot or 'N/A'})"),
                        days_until_due=days,
                    )
                )

        # 2. Fetch active prescriptions
        prescriptions = await self._repo.get_prescriptions_by_dog(dog_id)
        for p in prescriptions:
            if p.is_active:
                end_raw = getattr(p, "end_at", getattr(p, "end_date", None))
                end_date = (
                    end_raw.date()
                    if (end_raw is not None and hasattr(end_raw, "date"))
                    else end_raw
                )
                medications.append(
                    DogMedicalReminderItem(
                        id=f"rx-{p.id}",
                        kind="medication",
                        title=f"{p.drug_name} {p.dosage}",
                        due_date=end_date,
                        status="active",
                        details=f"Route: {getattr(p, 'route', 'N/A')}, Frequency: {getattr(p, 'frequency', 'Daily')}",
                        days_until_due=(end_date - today).days if end_date else None,
                    )
                )

        # 3. Fetch treatments for preventative care (deworming, flea/tick)
        treatments = await self._repo.get_treatments_by_dog(dog_id)
        for t in treatments:
            t_type = (t.treatment_type or "").lower()
            t_raw = getattr(t, "treatment_date", None)
            t_date = t_raw.date() if (t_raw is not None and hasattr(t_raw, "date")) else t_raw
            if any(term in t_type for term in ("deworm", "flea", "tick", "prevent", "parasite")):
                preventative_care.append(
                    DogMedicalReminderItem(
                        id=f"prev-{t.id}",
                        kind="preventative_care",
                        title=t.treatment_type.title(),
                        due_date=t_date,
                        status="active",
                        details=t.description,
                        days_until_due=None,
                    )
                )

        all_reminders = vaccinations + medications + preventative_care
        overdue_count = sum(1 for r in all_reminders if r.status == "overdue")
        upcoming_count = sum(1 for r in all_reminders if r.status in ("upcoming", "due_today"))

        return DogMedicalRemindersResponse(
            dog_id=dog_id,
            dog_name=dog_name,
            total_reminders=len(all_reminders),
            overdue_count=overdue_count,
            upcoming_count=upcoming_count,
            reminders=all_reminders,
            vaccinations=vaccinations,
            medications=medications,
            preventative_care=preventative_care,
        )
