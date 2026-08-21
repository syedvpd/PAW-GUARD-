"""Unit tests for MedicalService with mocked repository."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
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
    MedicalClearanceCreate,
    MedicalTreatmentCreate,
    MedicationAdministrationCreate,
    PrescriptionCreate,
    PrescriptionUpdate,
    VaccinationRecordCreate,
    VaccineProtocolCreate,
)
from pawguard.modules.medical.service import MedicalService
from pawguard.services.audit_service import AuditService


class TestMedicalService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=MedicalRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        repo = AsyncMock(spec=DogRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_audit):
        return MedicalService(mock_repo, mock_dog_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_perform_clinical_exam(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        exam_id = uuid.uuid4()
        mock_repo.create_clinical_exam.return_value = ClinicalExam(
            id=exam_id,
            dog_id=dog_id,
            vet_id=uuid.uuid4(),
            exam_date=datetime.now(UTC),
            body_condition_score=5,
            triage_diagnosis="Healthy",
        )
        payload = ClinicalExamCreate(
            dog_id=dog_id, body_condition_score=5, triage_diagnosis="Healthy"
        )
        result = await service.perform_clinical_exam(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.triage_diagnosis == "Healthy"

    @pytest.mark.asyncio
    async def test_perform_clinical_exam_dog_not_found(self, service, mock_dog_repo):
        mock_dog_repo.get_by_id.return_value = None
        payload = ClinicalExamCreate(
            dog_id=uuid.uuid4(), body_condition_score=5, triage_diagnosis="X"
        )
        with pytest.raises(NotFoundError, match="Dog profile not found"):
            await service.perform_clinical_exam(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_record_treatment(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        treatment_id = uuid.uuid4()
        mock_repo.create_treatment.return_value = MedicalTreatment(
            id=treatment_id,
            dog_id=dog_id,
            vet_id=uuid.uuid4(),
            treatment_date=datetime.now(UTC),
            treatment_type="surgery",
            description="Leg surgery",
        )
        payload = MedicalTreatmentCreate(
            dog_id=dog_id, treatment_type="surgery", description="Leg surgery"
        )
        result = await service.record_treatment(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.treatment_type == "surgery"

    @pytest.mark.asyncio
    async def test_administer_vaccine(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        vacc_id = uuid.uuid4()
        mock_repo.create_vaccination.return_value = VaccinationRecord(
            id=vacc_id,
            dog_id=dog_id,
            administered_by=uuid.uuid4(),
            administered_at=datetime.now(UTC),
            vaccine_name="Rabies",
        )
        mock_repo.get_vaccine_protocol_by_name.return_value = None
        payload = VaccinationRecordCreate(dog_id=dog_id, vaccine_name="Rabies")
        result = await service.administer_vaccine(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.vaccine_name == "Rabies"

    @pytest.mark.asyncio
    async def test_prescribe_medication(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        rx_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.create_prescription.return_value = Prescription(
            id=rx_id,
            dog_id=dog_id,
            vet_id=uuid.uuid4(),
            drug_name="Amoxicillin",
            dosage="500mg",
            route="Oral",
            start_at=now,
            end_at=now,
            is_active=True,
        )
        payload = PrescriptionCreate(
            dog_id=dog_id,
            drug_name="Amoxicillin",
            dosage="500mg",
            route="Oral",
            start_at=now,
            end_at=now,
        )
        result = await service.prescribe_medication(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.drug_name == "Amoxicillin"

    @pytest.mark.asyncio
    async def test_authorize_adoption_clearance(self, service, mock_dog_repo):
        dog_id = uuid.uuid4()
        dog = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
            is_quarantine_passed=False,
        )
        mock_dog_repo.get_by_id.return_value = dog
        result = await service.authorize_adoption_clearance(
            dog_id,
            roles={"veterinarian"},
            actor_id=uuid.uuid4(),
        )
        assert result is True
        assert dog.is_adoptable is True
        assert dog.is_quarantine_passed is True

    @pytest.mark.asyncio
    async def test_authorize_adoption_clearance_forbidden(self, service):
        with pytest.raises(ForbiddenError, match="require a veterinarian"):
            await service.authorize_adoption_clearance(uuid.uuid4(), roles={"user"})

    @pytest.mark.asyncio
    async def test_list_exams_paginated(self, service, mock_repo):
        now = datetime.now(UTC)
        exam = ClinicalExam(
            id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            exam_date=now,
            body_condition_score=5,
            triage_diagnosis="Healthy",
            created_at=now,
            updated_at=now,
        )
        mock_repo.list_exams_paginated.return_value = ([exam], 1)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_exams_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_exam(self, service, mock_repo):
        exam_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ClinicalExam(
            id=exam_id,
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            exam_date=datetime.now(UTC),
            body_condition_score=5,
            triage_diagnosis="Healthy",
        )
        mock_repo._session.execute.return_value = mock_result
        await service.soft_delete_exam(exam_id, actor_id=uuid.uuid4())
        assert mock_repo._session.flush.called

    @pytest.mark.asyncio
    async def test_soft_delete_exam_not_found(self, service, mock_repo):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_repo._session.execute.return_value = mock_result
        with pytest.raises(NotFoundError):
            await service.soft_delete_exam(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_soft_delete_treatment(self, service, mock_repo):
        treatment_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MedicalTreatment(
            id=treatment_id,
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            treatment_date=datetime.now(UTC),
            treatment_type="surgery",
            description="Surgery",
        )
        mock_repo._session.execute.return_value = mock_result
        await service.soft_delete_treatment(treatment_id, actor_id=uuid.uuid4())
        assert mock_repo._session.flush.called

    @pytest.mark.asyncio
    async def test_soft_delete_vaccination(self, service, mock_repo):
        vacc_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = VaccinationRecord(
            id=vacc_id,
            dog_id=uuid.uuid4(),
            administered_by=uuid.uuid4(),
            administered_at=datetime.now(UTC),
            vaccine_name="Rabies",
        )
        mock_repo._session.execute.return_value = mock_result
        await service.soft_delete_vaccination(vacc_id, actor_id=uuid.uuid4())
        assert mock_repo._session.flush.called

    @pytest.mark.asyncio
    async def test_soft_delete_prescription(self, service, mock_repo):
        rx_id = uuid.uuid4()
        mock_repo.get_prescription_by_id.return_value = Prescription(
            id=rx_id,
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            drug_name="Amox",
            dosage="500mg",
            route="Oral",
            start_at=datetime.now(UTC),
            end_at=datetime.now(UTC),
            is_active=True,
        )
        await service.soft_delete_prescription(rx_id, actor_id=uuid.uuid4())
        assert mock_repo._session.flush.called

    @pytest.mark.asyncio
    async def test_update_prescription(self, service, mock_repo):
        rx_id = uuid.uuid4()
        rx = Prescription(
            id=rx_id,
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            drug_name="Amox",
            dosage="500mg",
            route="Oral",
            start_at=datetime.now(UTC),
            end_at=datetime.now(UTC),
            is_active=True,
        )
        mock_repo.get_prescription_by_id.return_value = rx
        payload = PrescriptionUpdate(dosage="1g")
        result = await service.update_prescription(rx_id, payload, actor_id=uuid.uuid4())
        assert result.dosage == "1g"

    @pytest.mark.asyncio
    async def test_list_treatments_paginated(self, service, mock_repo):
        now = datetime.now(UTC)
        treatment = MedicalTreatment(
            id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            vet_id=uuid.uuid4(),
            treatment_date=now,
            treatment_type="therapy",
            description="Physio",
            created_at=now,
            updated_at=now,
        )
        mock_repo.list_treatments_paginated.return_value = ([treatment], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_treatments_paginated(page, sort)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_record_treatment_with_inventory_consumption(
        self, mock_repo, mock_dog_repo, mock_audit
    ):
        from unittest.mock import AsyncMock as _AsyncMock

        mock_inventory = _AsyncMock(spec=InventoryService)
        service = MedicalService(
            mock_repo, mock_dog_repo, mock_audit, inventory_service=mock_inventory
        )
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        treatment_id = uuid.uuid4()
        mock_repo.create_treatment.return_value = MedicalTreatment(
            id=treatment_id,
            dog_id=dog_id,
            vet_id=uuid.uuid4(),
            treatment_date=datetime.now(UTC),
            treatment_type="surgery",
            description="Leg surgery",
        )
        item_id = uuid.uuid4()
        payload = MedicalTreatmentCreate(
            dog_id=dog_id,
            treatment_type="surgery",
            description="Leg surgery",
            inventory_consumptions=[{"item_id": item_id, "quantity": 2.0}],
        )
        vet_id = uuid.uuid4()
        await service.record_treatment(vet_id, payload, actor_id=uuid.uuid4())
        mock_inventory.record_movement.assert_awaited_once()
        _, kwargs = mock_inventory.record_movement.await_args
        assert kwargs["user_id"] == vet_id
        assert kwargs["payload"].reference_type == "medical_treatment"
        assert kwargs["payload"].reference_id == treatment_id
        assert kwargs["payload"].item_id == item_id
        assert kwargs["payload"].quantity == 2.0

    @pytest.mark.asyncio
    async def test_prescribe_medication_with_inventory_consumption(
        self, mock_repo, mock_dog_repo, mock_audit
    ):
        from unittest.mock import AsyncMock as _AsyncMock

        mock_inventory = _AsyncMock(spec=InventoryService)
        service = MedicalService(
            mock_repo, mock_dog_repo, mock_audit, inventory_service=mock_inventory
        )
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        rx_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.create_prescription.return_value = Prescription(
            id=rx_id,
            dog_id=dog_id,
            vet_id=uuid.uuid4(),
            drug_name="Amoxicillin",
            dosage="500mg",
            route="Oral",
            start_at=now,
            end_at=now,
            is_active=True,
        )
        item_id = uuid.uuid4()
        payload = PrescriptionCreate(
            dog_id=dog_id,
            drug_name="Amoxicillin",
            dosage="500mg",
            route="Oral",
            start_at=now,
            end_at=now,
            inventory_consumptions=[{"item_id": item_id, "quantity": 1.0}],
        )
        await service.prescribe_medication(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        mock_inventory.record_movement.assert_awaited_once()
        _, kwargs = mock_inventory.record_movement.await_args
        assert kwargs["payload"].reference_type == "prescription"
        assert kwargs["payload"].reference_id == rx_id

    @pytest.mark.asyncio
    async def test_no_inventory_calls_without_consumptions(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        mock_repo.create_treatment.return_value = MedicalTreatment(
            id=uuid.uuid4(),
            dog_id=dog_id,
            vet_id=uuid.uuid4(),
            treatment_date=datetime.now(UTC),
            treatment_type="surgery",
            description="Leg surgery",
        )
        payload = MedicalTreatmentCreate(
            dog_id=dog_id, treatment_type="surgery", description="Leg surgery"
        )
        await service.record_treatment(uuid.uuid4(), payload, actor_id=uuid.uuid4())


class TestMedicalPrr35:
    """Unit tests for PRR 3.5 audit-finding fixes: medication sign-off register,
    protocol-driven vaccine auto-scheduling, and persisted adoption clearances."""

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=MedicalRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        repo = AsyncMock(spec=DogRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_audit):
        return MedicalService(mock_repo, mock_dog_repo, mock_audit)

    @staticmethod
    def _dog(dog_id: uuid.UUID) -> DogProfile:
        return DogProfile(
            id=dog_id,
            registration_number="DOG-001",
            name="B",
            breed="Mix",
            gender="male",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )

    @pytest.mark.asyncio
    async def test_log_medication_administration(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = self._dog(dog_id)
        log_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.create_administration.return_value = MedicationAdministrationLog(
            id=log_id,
            dog_id=dog_id,
            administered_by_id=uuid.uuid4(),
            medication_name="Amoxicillin",
            dosage="5ml",
            route="Oral",
            administered_at=now,
            notes="Given with food.",
        )
        payload = MedicationAdministrationCreate(
            dog_id=dog_id,
            medication_name="Amoxicillin",
            dosage="5ml",
            route="Oral",
            notes="Given with food.",
        )
        result = await service.log_medication_administration(
            uuid.uuid4(),
            payload,
            actor_id=uuid.uuid4(),
        )
        assert result.id == log_id
        assert result.medication_name == "Amoxicillin"
        created = mock_repo.create_administration.await_args.args[0]
        assert isinstance(created, MedicationAdministrationLog)
        assert created.dog_id == dog_id
        assert created.prescription_id is None
        assert created.notes == "Given with food."

    @pytest.mark.asyncio
    async def test_log_medication_administration_dog_not_found(self, service, mock_dog_repo):
        mock_dog_repo.get_by_id.return_value = None
        payload = MedicationAdministrationCreate(
            dog_id=uuid.uuid4(),
            medication_name="Amox",
            dosage="5ml",
            route="Oral",
        )
        with pytest.raises(NotFoundError, match="Dog profile not found"):
            await service.log_medication_administration(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_log_medication_administration_prescription_not_found(
        self, service, mock_repo, mock_dog_repo
    ):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = self._dog(dog_id)
        mock_repo.get_prescription_by_id.return_value = None
        payload = MedicationAdministrationCreate(
            prescription_id=uuid.uuid4(),
            dog_id=dog_id,
            medication_name="Amox",
            dosage="5ml",
            route="Oral",
        )
        with pytest.raises(NotFoundError, match="Prescription not found"):
            await service.log_medication_administration(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_schedule_next_dose_creates_due_record(self, service, mock_repo):
        dog_id = uuid.uuid4()
        now = datetime.now(UTC)
        rec = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=dog_id,
            administered_by=uuid.uuid4(),
            administered_at=now,
            vaccine_name="Rabies",
        )
        mock_repo.get_vaccine_protocol_by_name.return_value = VaccineProtocol(
            id=uuid.uuid4(),
            name="Rabies",
            default_interval_days=365,
            is_required=True,
        )
        next_rec = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=dog_id,
            administered_by=rec.administered_by,
            administered_at=now + timedelta(days=365),
            vaccine_name="Rabies",
        )
        mock_repo.create_vaccination.return_value = next_rec

        result = await service.schedule_next_dose(rec)

        assert result is next_rec
        assert rec.next_due_at is not None
        assert (rec.next_due_at - now).days == 365
        mock_repo.get_vaccine_protocol_by_name.assert_awaited_once_with("Rabies")
        created = mock_repo.create_vaccination.await_args.args[0]
        assert isinstance(created, VaccinationRecord)
        assert created.dog_id == dog_id
        assert created.vaccine_name == "Rabies"
        assert created.next_due_at is None
        assert created.administered_at == rec.next_due_at

    @pytest.mark.asyncio
    async def test_schedule_next_dose_skips_without_protocol(self, service, mock_repo):
        now = datetime.now(UTC)
        rec = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            administered_by=uuid.uuid4(),
            administered_at=now,
            vaccine_name="DHPP",
        )
        mock_repo.get_vaccine_protocol_by_name.return_value = None

        result = await service.schedule_next_dose(rec)

        assert result is None
        assert rec.next_due_at is None
        mock_repo.create_vaccination.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_schedule_next_dose_skips_when_already_scheduled(self, service, mock_repo):
        now = datetime.now(UTC)
        rec = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            administered_by=uuid.uuid4(),
            administered_at=now,
            vaccine_name="Rabies",
            next_due_at=now,
        )
        result = await service.schedule_next_dose(rec)
        assert result is None
        mock_repo.get_vaccine_protocol_by_name.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_administer_vaccine_auto_schedules_next_dose(
        self, service, mock_repo, mock_dog_repo
    ):
        dog_id = uuid.uuid4()
        vet_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = self._dog(dog_id)
        now = datetime.now(UTC)
        rec = VaccinationRecord(
            id=uuid.uuid4(),
            dog_id=dog_id,
            administered_by=vet_id,
            administered_at=now,
            vaccine_name="Rabies",
        )
        mock_repo.create_vaccination.return_value = rec
        mock_repo.get_vaccine_protocol_by_name.return_value = VaccineProtocol(
            id=uuid.uuid4(),
            name="Rabies",
            default_interval_days=90,
            is_required=False,
        )
        payload = VaccinationRecordCreate(dog_id=dog_id, vaccine_name="Rabies")
        result = await service.administer_vaccine(vet_id, payload, actor_id=uuid.uuid4())
        assert result.id == rec.id
        assert result.next_due_at is not None
        assert mock_repo.create_vaccination.await_count == 2

    @pytest.mark.asyncio
    async def test_create_vaccine_protocol(self, service, mock_repo):
        mock_repo.get_vaccine_protocol_by_name.return_value = None
        mock_repo.create_vaccine_protocol.return_value = VaccineProtocol(
            id=uuid.uuid4(),
            name="Rabies",
            default_interval_days=365,
            is_required=True,
        )
        payload = VaccineProtocolCreate(name="Rabies", default_interval_days=365)
        result = await service.create_vaccine_protocol(payload, actor_id=uuid.uuid4())
        assert result.name == "Rabies"
        assert result.default_interval_days == 365

    @pytest.mark.asyncio
    async def test_create_vaccine_protocol_conflict(self, service, mock_repo):
        from pawguard.core.exceptions import ConflictError

        mock_repo.get_vaccine_protocol_by_name.return_value = VaccineProtocol(
            id=uuid.uuid4(),
            name="Rabies",
            default_interval_days=365,
            is_required=True,
        )
        payload = VaccineProtocolCreate(name="Rabies", default_interval_days=365)
        with pytest.raises(ConflictError, match="already exists"):
            await service.create_vaccine_protocol(payload)

    @pytest.mark.asyncio
    async def test_authorize_adoption_clearance_persists_record(
        self, service, mock_repo, mock_dog_repo
    ):
        dog_id = uuid.uuid4()
        vet_id = uuid.uuid4()
        dog = self._dog(dog_id)
        mock_dog_repo.get_by_id.return_value = dog

        result = await service.authorize_adoption_clearance(
            dog_id,
            roles={"veterinarian"},
            actor_id=vet_id,
            payload=MedicalClearanceCreate(
                clearance_type="adoption_surgery",
                status="approved",
                decision_notes="Healthy.",
            ),
        )

        assert result is True
        assert dog.is_adoptable is True
        assert dog.is_quarantine_passed is True
        mock_repo.create_clearance.assert_awaited_once()
        clearance = mock_repo.create_clearance.await_args.args[0]
        assert isinstance(clearance, MedicalClearance)
        assert clearance.dog_id == dog_id
        assert clearance.authorized_by_id == vet_id
        assert clearance.status == "approved"
        assert clearance.clearance_type == "adoption_surgery"
        assert clearance.decision_notes == "Healthy."

    @pytest.mark.asyncio
    async def test_authorize_adoption_clearance_denied_keeps_dog_unadoptable(
        self, service, mock_repo, mock_dog_repo
    ):
        dog_id = uuid.uuid4()
        dog = self._dog(dog_id)
        mock_dog_repo.get_by_id.return_value = dog

        result = await service.authorize_adoption_clearance(
            dog_id,
            roles={"veterinarian"},
            actor_id=uuid.uuid4(),
            payload=MedicalClearanceCreate(status="denied", decision_notes="Not ready."),
        )

        assert result is True
        assert dog.is_adoptable is False
        clearance = mock_repo.create_clearance.await_args.args[0]
        assert clearance.status == "denied"

    @pytest.mark.asyncio
    async def test_get_clearances_for_dog(self, service, mock_repo):
        dog_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_repo.get_clearances_by_dog.return_value = [
            MedicalClearance(
                id=uuid.uuid4(),
                dog_id=dog_id,
                authorized_by_id=uuid.uuid4(),
                clearance_type="adoption_surgery",
                status="approved",
                authorized_at=now,
                created_at=now,
                updated_at=now,
            )
        ]
        result = await service.get_clearances_for_dog(dog_id)
        assert len(result) == 1
        assert result[0].status == "approved"
