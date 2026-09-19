"""Unit tests for Phase 1 applicant document handling (PRR 3.7)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.modules.adoption.models import (
    AdoptionApplication,
    AdoptionStatus,
    ApplicantDocumentType,
)
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.adoption.schemas import ApplicantDocumentCreate
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.dog.repository import DogRepository


def _app(status: AdoptionStatus, **kw) -> AdoptionApplication:
    return AdoptionApplication(
        id=uuid.uuid4(),
        dog_id=uuid.uuid4(),
        adopter_id=uuid.uuid4(),
        status=status,
        residential_status=kw.pop("residential_status", "owned"),
        is_foster_to_adopt=False,
        **kw,
    )


def _doc(doc_type: ApplicantDocumentType) -> ApplicantDocumentCreate:
    return ApplicantDocumentCreate(
        doc_type=doc_type,
        media_key=f"documents/{uuid.uuid4().hex}.pdf",
        filename="doc.pdf",
        mime_type="application/pdf",
    )


@pytest.fixture
def repo():
    repo = AsyncMock(spec=AdoptionRepository)
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def service(repo):
    return AdoptionService(repo, AsyncMock(spec=DogRepository))


@pytest.mark.asyncio
async def test_bulk_status_update_cannot_skip_document_verification(service, repo):
    repo.get_by_ids.return_value = [_app(AdoptionStatus.SCREENING)]

    with pytest.raises(ValidationFailedError, match="identity documents"):
        await service.bulk_update_status([uuid.uuid4()], AdoptionStatus.INTERVIEW)
    repo.bulk_update_status.assert_not_called()


@pytest.mark.asyncio
async def test_documents_cannot_be_added_to_closed_application(service, repo):
    repo.get_by_id.return_value = _app(AdoptionStatus.REJECTED)

    with pytest.raises(ValidationFailedError, match="closed application"):
        await service.add_applicant_document(
            uuid.uuid4(), _doc(ApplicantDocumentType.IDENTITY_PROOF)
        )


@pytest.mark.asyncio
async def test_document_added_after_interview_keeps_verification(service, repo):
    verified_at = datetime.now(UTC)
    app = _app(AdoptionStatus.INTERVIEW, documents_verified_at=verified_at)
    repo.get_by_id.return_value = app

    await service.add_applicant_document(app.id, _doc(ApplicantDocumentType.PET_MEDICAL_RECORD))

    assert app.documents_verified_at == verified_at
    assert app.applicant_documents[0]["doc_type"] == "pet_medical_record"


@pytest.mark.asyncio
async def test_documents_cannot_be_verified_after_screening(service, repo):
    repo.get_by_id.return_value = _app(
        AdoptionStatus.INTERVIEW,
        applicant_documents=[{"id": "d1", "doc_type": "identity_proof"}],
    )

    with pytest.raises(ValidationFailedError, match="submitted or in screening"):
        await service.verify_applicant_documents(uuid.uuid4())


@pytest.mark.asyncio
async def test_verification_records_the_verifier(service, repo):
    actor_id = uuid.uuid4()
    app = _app(
        AdoptionStatus.SCREENING,
        applicant_documents=[{"id": "d1", "doc_type": "identity_proof"}],
    )
    repo.get_by_id.return_value = app

    await service.verify_applicant_documents(app.id, actor_id=actor_id)

    assert app.documents_verified_at is not None
    assert app.documents_verified_by_id == actor_id


@pytest.mark.asyncio
async def test_removing_document_during_screening_clears_verification(service, repo):
    app = _app(
        AdoptionStatus.SCREENING,
        applicant_documents=[
            {"id": "d1", "doc_type": "identity_proof", "object_key": "documents/a.pdf"},
            {"id": "d2", "doc_type": "other", "object_key": "documents/b.pdf"},
        ],
        documents_verified_at=datetime.now(UTC),
    )
    repo.get_by_id.return_value = app

    await service.remove_applicant_document(app.id, "d2")

    assert [d["id"] for d in app.applicant_documents] == ["d1"]
    assert app.documents_verified_at is None


@pytest.mark.asyncio
async def test_removing_unknown_document_is_not_found(service, repo):
    repo.get_by_id.return_value = _app(AdoptionStatus.SCREENING, applicant_documents=[])

    with pytest.raises(NotFoundError):
        await service.remove_applicant_document(uuid.uuid4(), "missing")


@pytest.mark.asyncio
async def test_documents_cannot_be_removed_from_completed_application(service, repo):
    repo.get_by_id.return_value = _app(
        AdoptionStatus.COMPLETED,
        applicant_documents=[{"id": "d1", "doc_type": "identity_proof", "object_key": "k"}],
    )

    with pytest.raises(ValidationFailedError, match="closed application"):
        await service.remove_applicant_document(uuid.uuid4(), "d1")
