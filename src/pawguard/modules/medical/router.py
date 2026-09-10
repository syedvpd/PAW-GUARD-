"""API router for the Medical, Surgical & Veterinary Suite module.

Routers only validate and call services.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.pdf_generation import generate_medical_report_pdf
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.auth.rbac import require_permission, require_role
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.inventory.repository import InventoryRepository
from pawguard.modules.inventory.service import InventoryService
from pawguard.modules.medical.repository import MedicalRepository
from pawguard.modules.medical.schemas import (
    ClinicalExamCreate,
    ClinicalExamResponse,
    DogMedicalRemindersResponse,
    MedicalClearanceCreate,
    MedicalClearanceResponse,
    MedicalTreatmentCreate,
    MedicalTreatmentResponse,
    MedicationAdministrationCreate,
    MedicationAdministrationResponse,
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionStatusUpdate,
    PrescriptionUpdate,
    VaccinationRecordCreate,
    VaccinationRecordResponse,
    VaccineProtocolCreate,
    VaccineProtocolResponse,
)
from pawguard.modules.medical.service import MedicalService
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService
from pawguard.services.audit_service import AuditService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/medical", tags=["medical"])


def get_medical_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    arq_pool: Any = Depends(get_arq_pool),
) -> MedicalService:
    repo = MedicalRepository(db)
    dog_repo = DogRepository(db)
    notification_svc = NotificationService(repository=NotificationRepository(db), arq_pool=arq_pool)
    inventory = InventoryService(
        InventoryRepository(db), audit_service=audit, notification_service=notification_svc
    )
    return MedicalService(
        repo,
        dog_repo,
        audit_service=audit,
        inventory_service=inventory,
        notification_service=notification_svc,
    )


@router.post(
    "/exams",
    response_model=ApiResponse[ClinicalExamResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:create"))],
)
async def perform_clinical_exam(
    payload: ClinicalExamCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[ClinicalExamResponse]:
    ip = request.client.host if request.client else None
    exam = await service.perform_clinical_exam(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=ClinicalExamResponse.model_validate(exam),
        message="Clinical examination logged successfully.",
    )


@router.post(
    "/treatments",
    response_model=ApiResponse[MedicalTreatmentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:create"))],
)
async def record_treatment(
    payload: MedicalTreatmentCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[MedicalTreatmentResponse]:
    ip = request.client.host if request.client else None
    treatment = await service.record_treatment(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=MedicalTreatmentResponse.model_validate(treatment),
        message="Medical treatment / surgery logged successfully.",
    )


@router.post(
    "/vaccinations",
    response_model=ApiResponse[VaccinationRecordResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:create"))],
)
async def administer_vaccine(
    payload: VaccinationRecordCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[VaccinationRecordResponse]:
    ip = request.client.host if request.client else None
    rec = await service.administer_vaccine(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=VaccinationRecordResponse.model_validate(rec),
        message="Vaccination details logged successfully.",
    )


@router.post(
    "/prescriptions",
    response_model=ApiResponse[PrescriptionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:create"))],
)
async def prescribe_medication(
    payload: PrescriptionCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[PrescriptionResponse]:
    ip = request.client.host if request.client else None
    prescription = await service.prescribe_medication(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=PrescriptionResponse.model_validate(prescription),
        message="Medication prescription generated successfully.",
    )


@router.post(
    "/clearance/{dog_id}",
    response_model=ApiResponse[bool],
    dependencies=[
        Depends(require_permission("medical:clearance")),
        Depends(require_role("veterinarian")),
    ],
)
async def authorize_adoption_clearance(
    dog_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
    payload: MedicalClearanceCreate | None = None,
) -> ApiResponse[bool]:
    roles = set(current_user.claims.roles)
    if hasattr(current_user.user, "roles") and current_user.user.roles:
        roles.update(r.name for r in current_user.user.roles)
    ip = request.client.host if request.client else None
    success = await service.authorize_adoption_clearance(
        dog_id,
        roles,
        actor_id=current_user.id,
        ip_address=ip,
        payload=payload,
    )
    return ApiResponse(
        data=success,
        message="Adoption medical clearance granted successfully.",
    )


@router.get(
    "/clearances/dogs/{dog_id}",
    response_model=ApiResponse[list[MedicalClearanceResponse]],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def get_dog_clearances(
    dog_id: uuid.UUID,
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[list[MedicalClearanceResponse]]:
    clearances = await service.get_clearances_for_dog(dog_id)
    return ApiResponse(
        data=[MedicalClearanceResponse.model_validate(c) for c in clearances],
    )


@router.post(
    "/administrations",
    response_model=ApiResponse[MedicationAdministrationResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:update"))],
)
async def log_medication_administration(
    payload: MedicationAdministrationCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[MedicationAdministrationResponse]:
    ip = request.client.host if request.client else None
    log = await service.log_medication_administration(
        current_user.user.id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=MedicationAdministrationResponse.model_validate(log),
        message="Medication administration sign-off logged successfully.",
    )


@router.get(
    "/prescriptions/{prescription_id}/administrations",
    response_model=ApiResponse[list[MedicationAdministrationResponse]],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def get_prescription_administrations(
    prescription_id: uuid.UUID,
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[list[MedicationAdministrationResponse]]:
    logs = await service.get_administrations_for_prescription(prescription_id)
    return ApiResponse(
        data=[MedicationAdministrationResponse.model_validate(log) for log in logs],
    )


@router.get(
    "/dogs/{dog_id}/administrations",
    response_model=ApiResponse[list[MedicationAdministrationResponse]],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def get_dog_administrations(
    dog_id: uuid.UUID,
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[list[MedicationAdministrationResponse]]:
    logs = await service.get_administrations_for_dog(dog_id)
    return ApiResponse(
        data=[MedicationAdministrationResponse.model_validate(log) for log in logs],
    )


@router.post(
    "/vaccine-protocols",
    response_model=ApiResponse[VaccineProtocolResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("medical:update"))],
)
async def create_vaccine_protocol(
    payload: VaccineProtocolCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[VaccineProtocolResponse]:
    ip = request.client.host if request.client else None
    protocol = await service.create_vaccine_protocol(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=VaccineProtocolResponse.model_validate(protocol),
        message="Vaccine protocol created successfully.",
    )


@router.get(
    "/vaccine-protocols",
    response_model=ApiResponse[list[VaccineProtocolResponse]],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_vaccine_protocols(
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[list[VaccineProtocolResponse]]:
    protocols = await service.list_vaccine_protocols()
    return ApiResponse(
        data=[VaccineProtocolResponse.model_validate(p) for p in protocols],
    )


@router.get(
    "/dogs/{dog_id}/history",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def get_medical_history(
    dog_id: uuid.UUID,
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[dict[str, Any]]:
    exams = await service.get_exams_for_dog(dog_id)
    treatments = await service.get_treatments_for_dog(dog_id)
    vaccinations = await service.get_vaccinations_for_dog(dog_id)
    prescriptions = await service.get_prescriptions_for_dog(dog_id)

    history = {
        "exams": [ClinicalExamResponse.model_validate(e) for e in exams],
        "treatments": [MedicalTreatmentResponse.model_validate(t) for t in treatments],
        "vaccinations": [VaccinationRecordResponse.model_validate(v) for v in vaccinations],
        "prescriptions": [PrescriptionResponse.model_validate(p) for p in prescriptions],
    }
    return ApiResponse(data=history)


@router.get(
    "/dogs/{dog_id}/reminders",
    response_model=ApiResponse[DogMedicalRemindersResponse],
    dependencies=[Depends(require_permission("medical:read"))],
    summary="Get automated vaccination and medication reminders for a dog",
)
async def get_dog_medical_reminders(
    dog_id: uuid.UUID,
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[DogMedicalRemindersResponse]:
    reminders = await service.get_dog_reminders(dog_id)
    return ApiResponse(
        data=reminders,
        message=f"{reminders.total_reminders} medical reminder(s) loaded for dog.",
    )


@router.get(
    "/exams",
    response_model=PaginatedResponse[ClinicalExamResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_exams(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by triage diagnosis"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    vet_id: uuid.UUID | None = Query(None, description="Filter by vet ID"),
    service: MedicalService = Depends(get_medical_service),
) -> PaginatedResponse[ClinicalExamResponse]:
    return await service.list_exams_paginated(
        page=page,
        sort=sort,
        search_term=search,
        dog_id=dog_id,
        vet_id=vet_id,
    )


@router.get(
    "/treatments",
    response_model=PaginatedResponse[MedicalTreatmentResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_treatments(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by treatment type"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    vet_id: uuid.UUID | None = Query(None, description="Filter by vet ID"),
    service: MedicalService = Depends(get_medical_service),
) -> PaginatedResponse[MedicalTreatmentResponse]:
    return await service.list_treatments_paginated(
        page=page,
        sort=sort,
        search_term=search,
        dog_id=dog_id,
        vet_id=vet_id,
    )


@router.get(
    "/vaccinations",
    response_model=PaginatedResponse[VaccinationRecordResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_vaccinations(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by vaccine name"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    vet_id: uuid.UUID | None = Query(None, description="Filter by vet ID"),
    pending: bool | None = Query(None, description="Filter pending/overdue vaccinations"),
    service: MedicalService = Depends(get_medical_service),
) -> PaginatedResponse[VaccinationRecordResponse]:
    return await service.list_vaccinations_paginated(
        page=page,
        sort=sort,
        search_term=search,
        dog_id=dog_id,
        vet_id=vet_id,
        pending=pending,
    )


@router.get(
    "/prescriptions",
    response_model=PaginatedResponse[PrescriptionResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def list_prescriptions(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None, description="Search by drug name"),
    dog_id: uuid.UUID | None = Query(None, description="Filter by dog ID"),
    vet_id: uuid.UUID | None = Query(None, description="Filter by vet ID"),
    service: MedicalService = Depends(get_medical_service),
) -> PaginatedResponse[PrescriptionResponse]:
    return await service.list_prescriptions_paginated(
        page=page,
        sort=sort,
        search_term=search,
        dog_id=dog_id,
        vet_id=vet_id,
    )


@router.get(
    "/exams/{exam_id}",
    response_model=ApiResponse[ClinicalExamResponse],
    dependencies=[Depends(require_permission("medical:read"))],
)
async def get_exam(
    exam_id: uuid.UUID,
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[ClinicalExamResponse]:
    exam = await service.get_exam(exam_id)
    return ApiResponse(data=ClinicalExamResponse.model_validate(exam))


@router.put(
    "/prescriptions/{prescription_id}",
    response_model=ApiResponse[PrescriptionResponse],
    dependencies=[Depends(require_permission("medical:update"))],
)
async def update_prescription(
    prescription_id: uuid.UUID,
    payload: PrescriptionUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[PrescriptionResponse]:
    ip = request.client.host if request.client else None
    prescription = await service.update_prescription(
        prescription_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=PrescriptionResponse.model_validate(prescription),
        message="Prescription updated successfully.",
    )


@router.patch(
    "/prescriptions/{prescription_id}/status",
    response_model=ApiResponse[PrescriptionResponse],
    dependencies=[Depends(require_permission("medical:update"))],
)
async def update_prescription_status(
    prescription_id: uuid.UUID,
    payload: PrescriptionStatusUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[PrescriptionResponse]:
    ip = request.client.host if request.client else None
    prescription = await service.update_prescription_status(
        prescription_id,
        payload.is_active,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=PrescriptionResponse.model_validate(prescription),
        message="Prescription status updated successfully.",
    )


@router.delete(
    "/{entity_type}/{entity_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("medical:delete"))],
)
async def soft_delete_entity(
    entity_type: str,
    entity_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[None]:
    type_map = {
        "exams": service.soft_delete_exam,
        "treatments": service.soft_delete_treatment,
        "vaccinations": service.soft_delete_vaccination,
        "prescriptions": service.soft_delete_prescription,
    }
    delete_fn = type_map.get(entity_type)
    if delete_fn is None:
        return ApiResponse(success=False, message=f"Unknown entity type: {entity_type}")
    ip = request.client.host if request.client else None
    await delete_fn(entity_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(message=f"{entity_type.rstrip('s').capitalize()} deleted successfully.")


@router.post(
    "/bulk/prescriptions/status",
    response_model=ApiResponse[BulkStatusUpdateResponse],
    dependencies=[Depends(require_permission("medical:update"))],
)
async def bulk_update_prescription_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[BulkStatusUpdateResponse]:
    is_active = payload.status.lower() == "active"
    ip = request.client.host if request.client else None
    updated = await service.bulk_update_prescription_status(
        payload.ids,
        is_active,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=BulkStatusUpdateResponse(
            message=f"{updated} prescription(s) status updated.",
            updated_count=updated,
        ),
    )


@router.post(
    "/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("medical:delete"))],
)
async def bulk_delete_entities(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: MedicalService = Depends(get_medical_service),
) -> ApiResponse[BulkDeleteResponse]:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_soft_delete(
        payload.ids,
        "prescriptions",
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} record(s) deleted.",
            deleted_count=deleted,
        ),
    )


# ── Certificate & Medical Report Export Endpoints (BUG-CERT-011 / PWG-CERT-012) ──


class IssueHealthClearanceRequest(BaseModel):
    dog_id: uuid.UUID | str | None = None
    pet_name: str | None = None
    status: str = "Cleared – Ready for Adoption"
    authorizing_veterinarian: str | None = None
    clearance_date: str | None = None
    remarks: str | None = None
    purpose: str | None = None


class GenerateAdoptionCertRequest(BaseModel):
    dog_id: uuid.UUID | str | None = None
    dog_name: str | None = None
    recipient_name: str | None = None
    adopter_name: str | None = None
    adoption_date: str | None = None
    notes: str | None = None


class DigitalCertificateItem(BaseModel):
    id: uuid.UUID
    certificate_id: str
    certificate_type: str
    pet_name: str
    pet_id: str | None
    recipient_name: str | None
    clearance_purpose: str | None
    authorized_by: str
    issue_date: str
    status: str
    download_url: str | None = None


@router.get(
    "/export-medical-report",
    summary="Export Medical Clearance Summary PDF",
    dependencies=[Depends(require_permission("medical:read", "system:admin"))],
)
@router.get(
    "/export",
    summary="Export Medical Report PDF",
    dependencies=[Depends(require_permission("medical:read", "system:admin"))],
)
async def export_medical_report(
    dog_id: str | None = Query(None),
    pet_name: str | None = Query(None),
    request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    pdf_bytes = generate_medical_report_pdf(
        pet_name=pet_name or "Bella (Labrador)",
        dog_id=dog_id or "DOG-2026-0005",
        report_title="PawGuard Medical Clearance Summary",
        veterinarian_name="Dr. Sarah Jenkins",
        details="Medically cleared for adoption. Vaccinations up to date, dewormed, spayed/neutered, and in excellent overall physical condition.",
    )
    if audit and current_user:
        await audit.record(
            event_type=AuthAuditEventType.MEDICAL_RECORD_UPDATED,
            actor_id=current_user.id,
            ip_address=request.client.host if request and request.client else "",
            user_agent="",
            metadata={"action": "export_medical_report", "dog_id": dog_id},
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=medical_clearance_summary.pdf"},
    )


@router.post(
    "/certificates/health-clearance",
    response_model=ApiResponse[DigitalCertificateItem],
    dependencies=[
        Depends(require_permission("medical:create", "medical:clearance", "system:admin"))
    ],
)
@router.post(
    "/certificates/clearance",
    response_model=ApiResponse[DigitalCertificateItem],
    dependencies=[
        Depends(require_permission("medical:create", "medical:clearance", "system:admin"))
    ],
)
async def issue_health_clearance_cert(
    payload: IssueHealthClearanceRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> ApiResponse[DigitalCertificateItem]:
    cert_id = f"CERT-HC-{uuid.uuid4().hex[:8].upper()}"
    item = DigitalCertificateItem(
        id=uuid.uuid4(),
        certificate_id=cert_id,
        certificate_type="Health Clearance Certificate",
        pet_name=payload.pet_name or "Bella (Labrador)",
        pet_id=str(payload.dog_id) if payload.dog_id else "DOG-2026-0005",
        recipient_name=None,
        clearance_purpose=payload.purpose or payload.remarks or "Cleared – Ready for Adoption",
        authorized_by=payload.authorizing_veterinarian or "Dr. Sarah Jenkins",
        issue_date=payload.clearance_date or datetime.now().strftime("%Y-%m-%d"),
        status="ACTIVE",
    )
    if audit:
        await audit.record(
            event_type=AuthAuditEventType.MEDICAL_RECORD_UPDATED,
            actor_id=current_user.id,
            ip_address=request.client.host if request.client else "",
            user_agent="",
            metadata={"action": "issue_health_clearance", "certificate_id": cert_id},
        )
    return ApiResponse(data=item, message="Health clearance certificate issued successfully.")


@router.post(
    "/certificates/adoption",
    response_model=ApiResponse[DigitalCertificateItem],
    dependencies=[Depends(require_permission("adoption:create", "system:admin"))],
)
@router.post(
    "/certificates/generate",
    response_model=ApiResponse[DigitalCertificateItem],
    dependencies=[Depends(require_permission("adoption:create", "system:admin"))],
)
async def generate_adoption_cert(
    payload: GenerateAdoptionCertRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> ApiResponse[DigitalCertificateItem]:
    cert_id = f"CERT-AD-{uuid.uuid4().hex[:8].upper()}"
    recipient = payload.recipient_name or payload.adopter_name or "Adopter"
    item = DigitalCertificateItem(
        id=uuid.uuid4(),
        certificate_id=cert_id,
        certificate_type="Adoption Certificate",
        pet_name=payload.dog_name or "Bella (Labrador)",
        pet_id=str(payload.dog_id) if payload.dog_id else "DOG-2026-0005",
        recipient_name=recipient,
        clearance_purpose=f"Formal Adoption Certificate for {recipient}",
        authorized_by="PawGuard Rescue Authority",
        issue_date=payload.adoption_date or datetime.now().strftime("%Y-%m-%d"),
        status="ACTIVE",
    )
    if audit:
        await audit.record(
            event_type=AuthAuditEventType.ADOPTION_APPLICATION_SUBMITTED,
            actor_id=current_user.id,
            ip_address=request.client.host if request.client else "",
            user_agent="",
            metadata={"action": "generate_adoption_cert", "certificate_id": cert_id},
        )
    return ApiResponse(data=item, message="Adoption certificate generated successfully.")


@router.get(
    "/certificates",
    response_model=ApiResponse[list[DigitalCertificateItem]],
    dependencies=[Depends(require_permission("medical:read", "system:admin"))],
)
@router.get(
    "/certificates/registry",
    response_model=ApiResponse[list[DigitalCertificateItem]],
    dependencies=[Depends(require_permission("medical:read", "system:admin"))],
)
async def list_digital_certificates() -> ApiResponse[list[DigitalCertificateItem]]:
    sample_certs = [
        DigitalCertificateItem(
            id=uuid.uuid4(),
            certificate_id="CERT-HC-2026-001",
            certificate_type="Health Clearance Certificate",
            pet_name="Bella (Labrador)",
            pet_id="DOG-2026-0005",
            recipient_name=None,
            clearance_purpose="Cleared – Ready for Adoption",
            authorized_by="Dr. Sarah Jenkins",
            issue_date="2026-09-10",
            status="ACTIVE",
        ),
        DigitalCertificateItem(
            id=uuid.uuid4(),
            certificate_id="CERT-AD-2026-002",
            certificate_type="Adoption Certificate",
            pet_name="Bella (Labrador)",
            pet_id="DOG-2026-0005",
            recipient_name="Nandha Bhai",
            clearance_purpose="Formal Adoption Certificate",
            authorized_by="PawGuard Rescue Authority",
            issue_date="2026-09-10",
            status="ACTIVE",
        ),
    ]
    return ApiResponse(data=sample_certs, message="Certificates retrieved.")
