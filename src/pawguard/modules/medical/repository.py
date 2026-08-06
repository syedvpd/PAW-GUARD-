"""Data access for the Medical, Surgical & Veterinary Suite module.

Repositories never contain business decisions.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.medical.models import (
    ClinicalExam,
    MedicalClearance,
    MedicalTreatment,
    MedicationAdministrationLog,
    Prescription,
    VaccinationRecord,
    VaccineProtocol,
)


class MedicalRepository:
    SEARCH_FIELDS = ("triage_diagnosis", "treatment_type", "vaccine_name", "drug_name")
    SORTABLE_FIELDS = {"created_at", "exam_date", "treatment_date", "vaccine_name", "drug_name"}

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_clinical_exam(self, exam: ClinicalExam) -> ClinicalExam:
        self._session.add(exam)
        await self._session.flush()
        await self._session.refresh(exam)
        return exam

    async def create_treatment(self, treatment: MedicalTreatment) -> MedicalTreatment:
        self._session.add(treatment)
        await self._session.flush()
        await self._session.refresh(treatment)
        return treatment

    async def create_vaccination(self, rec: VaccinationRecord) -> VaccinationRecord:
        self._session.add(rec)
        await self._session.flush()
        await self._session.refresh(rec)
        return rec

    async def create_prescription(self, prescription: Prescription) -> Prescription:
        self._session.add(prescription)
        await self._session.flush()
        await self._session.refresh(prescription)
        return prescription

    async def create_administration(
        self, log: MedicationAdministrationLog
    ) -> MedicationAdministrationLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def get_administrations_by_prescription(
        self, prescription_id: uuid.UUID
    ) -> Sequence[MedicationAdministrationLog]:
        stmt = (
            select(MedicationAdministrationLog)
            .where(
                MedicationAdministrationLog.prescription_id == prescription_id,
                MedicationAdministrationLog.deleted_at.is_(None),
            )
            .order_by(MedicationAdministrationLog.administered_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_administrations_by_dog(
        self, dog_id: uuid.UUID
    ) -> Sequence[MedicationAdministrationLog]:
        stmt = (
            select(MedicationAdministrationLog)
            .where(
                MedicationAdministrationLog.dog_id == dog_id,
                MedicationAdministrationLog.deleted_at.is_(None),
            )
            .order_by(MedicationAdministrationLog.administered_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def create_vaccine_protocol(self, protocol: VaccineProtocol) -> VaccineProtocol:
        self._session.add(protocol)
        await self._session.flush()
        return protocol

    async def list_vaccine_protocols(self) -> Sequence[VaccineProtocol]:
        stmt = (
            select(VaccineProtocol)
            .where(VaccineProtocol.deleted_at.is_(None))
            .order_by(VaccineProtocol.name.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_vaccine_protocol_by_name(self, name: str) -> VaccineProtocol | None:
        stmt = (
            select(VaccineProtocol)
            .where(
                func.lower(func.trim(VaccineProtocol.name)) == name.strip().lower(),
                VaccineProtocol.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_clearance(self, clearance: MedicalClearance) -> MedicalClearance:
        self._session.add(clearance)
        await self._session.flush()
        return clearance

    async def get_clearances_by_dog(self, dog_id: uuid.UUID) -> Sequence[MedicalClearance]:
        stmt = (
            select(MedicalClearance)
            .where(MedicalClearance.dog_id == dog_id, MedicalClearance.deleted_at.is_(None))
            .order_by(MedicalClearance.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_prescription_by_id(self, p_id: uuid.UUID) -> Prescription | None:
        stmt = (
            select(Prescription).where(
                Prescription.id == p_id, Prescription.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_exams_by_dog(self, dog_id: uuid.UUID) -> Sequence[ClinicalExam]:
        stmt = (
            select(ClinicalExam)
            .where(ClinicalExam.dog_id == dog_id, ClinicalExam.deleted_at.is_(None))
            .order_by(ClinicalExam.exam_date.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_treatments_by_dog(self, dog_id: uuid.UUID) -> Sequence[MedicalTreatment]:
        stmt = (
            select(MedicalTreatment)
            .where(MedicalTreatment.dog_id == dog_id, MedicalTreatment.deleted_at.is_(None))
            .order_by(MedicalTreatment.treatment_date.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_vaccinations_by_dog(self, dog_id: uuid.UUID) -> Sequence[VaccinationRecord]:
        stmt = (
            select(VaccinationRecord)
            .where(VaccinationRecord.dog_id == dog_id, VaccinationRecord.deleted_at.is_(None))
            .order_by(VaccinationRecord.administered_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_prescriptions_by_dog(self, dog_id: uuid.UUID) -> Sequence[Prescription]:
        stmt = (
            select(Prescription)
            .where(Prescription.dog_id == dog_id, Prescription.deleted_at.is_(None))
            .order_by(Prescription.start_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_active_prescriptions(self) -> Sequence[Prescription]:
        stmt = (
            select(Prescription)
            .where(Prescription.is_active, Prescription.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_exams_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        dog_id: uuid.UUID | None = None,
        vet_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[ClinicalExam], int]:
        stmt = select(ClinicalExam).where(ClinicalExam.deleted_at.is_(None))

        search_filter = build_search_filter(ClinicalExam, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if dog_id is not None:
            stmt = stmt.where(ClinicalExam.dog_id == dog_id)
        if vet_id is not None:
            stmt = stmt.where(ClinicalExam.vet_id == vet_id)

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS, "exam_date")

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_treatments_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        dog_id: uuid.UUID | None = None,
        vet_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[MedicalTreatment], int]:
        stmt = select(MedicalTreatment).where(MedicalTreatment.deleted_at.is_(None))

        search_filter = build_search_filter(MedicalTreatment, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if dog_id is not None:
            stmt = stmt.where(MedicalTreatment.dog_id == dog_id)
        if vet_id is not None:
            stmt = stmt.where(MedicalTreatment.vet_id == vet_id)

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS, "treatment_date")

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_vaccinations_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        dog_id: uuid.UUID | None = None,
        vet_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[VaccinationRecord], int]:
        stmt = select(VaccinationRecord).where(VaccinationRecord.deleted_at.is_(None))

        search_filter = build_search_filter(VaccinationRecord, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if dog_id is not None:
            stmt = stmt.where(VaccinationRecord.dog_id == dog_id)
        if vet_id is not None:
            stmt = stmt.where(VaccinationRecord.administered_by == vet_id)

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS, "vaccine_name")

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_prescriptions_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        dog_id: uuid.UUID | None = None,
        vet_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Prescription], int]:
        stmt = select(Prescription).where(Prescription.deleted_at.is_(None))

        search_filter = build_search_filter(Prescription, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if dog_id is not None:
            stmt = stmt.where(Prescription.dog_id == dog_id)
        if vet_id is not None:
            stmt = stmt.where(Prescription.vet_id == vet_id)

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS, "drug_name")

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_by_ids(self, ids: list[uuid.UUID]) -> Sequence[Prescription]:
        stmt = (
            select(Prescription)
            .where(Prescription.id.in_(ids), Prescription.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def bulk_update_prescription_status(self, ids: list[uuid.UUID], is_active: bool) -> int:
        stmt = (
            update(Prescription)
            .where(Prescription.id.in_(ids), Prescription.deleted_at.is_(None))
            .values(is_active=is_active)
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    async def bulk_soft_delete(self, entity_type: str, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        model_map = {
            "exams": ClinicalExam,
            "treatments": MedicalTreatment,
            "vaccinations": VaccinationRecord,
            "prescriptions": Prescription,
        }
        model = model_map.get(entity_type)
        if model is None:
            return 0
        stmt = (
            update(model)
            .where(model.id.in_(ids), model.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]
