"""MedicalService: owns all medical examinations, surgeries, prescriptions.

(RULE-003) — clearances behaviour.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from pawguard.core.exceptions import ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.medical.models import (
    ClinicalExam,
    MedicalTreatment,
    Prescription,
    VaccinationRecord,
)
from pawguard.modules.medical.repository import MedicalRepository
from pawguard.modules.medical.schemas import (
    ClinicalExamCreate,
    ClinicalExamResponse,
    MedicalTreatmentCreate,
    MedicalTreatmentResponse,
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionUpdate,
    VaccinationRecordCreate,
    VaccinationRecordResponse,
)
from pawguard.services.audit_service import AuditService


class MedicalService:
    def __init__(
        self,
        repository: MedicalRepository,
        dog_repo: DogRepository,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._dog_repo = dog_repo
        self._audit = audit_service

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
        return rec

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
        return prescription

    async def authorize_adoption_clearance(
        self,
        dog_id: uuid.UUID,
        roles: set[str],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> bool:
        if not ("super_admin" in roles or "veterinarian" in roles):
            raise ForbiddenError("Adoption medical clearances require a veterinarian's authority.")

        dog = await self._dog_repo.get_by_id(dog_id)
        if dog is None:
            raise NotFoundError("Dog profile not found.")

        dog.is_adoptable = True
        dog.is_quarantine_passed = True
        await self._dog_repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.MEDICAL_RECORD_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"dog_id": str(dog_id)},
            )
        return True

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
            page=page, sort=sort, search_term=search_term, dog_id=dog_id, vet_id=vet_id,
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
            page=page, sort=sort, search_term=search_term, dog_id=dog_id, vet_id=vet_id,
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
            page=page, sort=sort, search_term=search_term, dog_id=dog_id, vet_id=vet_id,
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
            page=page, sort=sort, search_term=search_term, dog_id=dog_id, vet_id=vet_id,
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

    async def _get_exam_by_id(
        self, exam_id: uuid.UUID
    ) -> ClinicalExam | None:
        from sqlalchemy import select

        stmt = select(ClinicalExam).where(
            ClinicalExam.id == exam_id,
            ClinicalExam.deleted_at.is_(None),
        )
        return (
            await self._repo._session.execute(stmt)
        ).scalar_one_or_none()

    async def _get_treatment_by_id(
        self, treatment_id: uuid.UUID
    ) -> MedicalTreatment | None:
        from sqlalchemy import select

        stmt = select(MedicalTreatment).where(
            MedicalTreatment.id == treatment_id,
            MedicalTreatment.deleted_at.is_(None),
        )
        return (
            await self._repo._session.execute(stmt)
        ).scalar_one_or_none()

    async def _get_vaccination_by_id(
        self, vaccination_id: uuid.UUID
    ) -> VaccinationRecord | None:
        from sqlalchemy import select

        stmt = select(VaccinationRecord).where(
            VaccinationRecord.id == vaccination_id,
            VaccinationRecord.deleted_at.is_(None),
        )
        return (
            await self._repo._session.execute(stmt)
        ).scalar_one_or_none()
