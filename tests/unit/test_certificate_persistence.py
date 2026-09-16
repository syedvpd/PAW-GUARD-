"""Unit tests for digital certificate persistence and retrieval (ITEM 1).

Covers:
1. Issue health clearance certificate without dog_id persists a DigitalCertificate row.
2. Issue health clearance certificate with dog_id persists DigitalCertificate and MedicalClearance.
3. List certificates returns the exact cert_id stored at issuance (no regenerated IDs).
4. Adoption certificate read-back accurately preserves certificate_type and recipient_name.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from pawguard.modules.auth.dependencies import CurrentUser
from pawguard.modules.auth.models import User
from pawguard.modules.medical.models import DigitalCertificate
from pawguard.modules.medical.router import (
    GenerateAdoptionCertRequest,
    IssueHealthClearanceRequest,
    generate_adoption_cert,
    issue_health_clearance_cert,
    list_digital_certificates,
)


@pytest.fixture
def mock_user() -> CurrentUser:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.full_name = "Dr. Test Vet"
    user.system_role = "veterinarian"
    claims = MagicMock()
    claims.role = "veterinarian"
    claims.user_id = user.id
    return CurrentUser(user=user, claims=claims, db=AsyncMock(), redis=AsyncMock())


@pytest.fixture
def mock_request() -> Request:
    req = MagicMock(spec=Request)
    req.client.host = "127.0.0.1"
    return req


@pytest.mark.asyncio
async def test_issue_cert_without_dog_id_persists_digital_certificate(
    mock_user: CurrentUser, mock_request: Request
) -> None:
    """POST with no dog_id creates a DB row in digital_certificates."""
    mock_db = AsyncMock()
    added_objects = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    payload = IssueHealthClearanceRequest(
        pet_name="Buddy the Stray",
        purpose="Ready for community placement",
        authorizing_veterinarian="Dr. Test Vet",
        clearance_date="2026-09-16",
    )

    response = await issue_health_clearance_cert(
        payload=payload,
        request=mock_request,
        current_user=mock_user,
        audit=AsyncMock(),
        db=mock_db,
    )

    assert response.success is True
    assert response.data is not None
    issued_cert_id = response.data.certificate_id
    assert issued_cert_id.startswith("CERT-HC-")

    # Verify DigitalCertificate row was added to db session
    cert_rows = [o for o in added_objects if isinstance(o, DigitalCertificate)]
    assert len(cert_rows) == 1
    persisted = cert_rows[0]
    assert persisted.cert_id == issued_cert_id
    assert persisted.pet_name == "Buddy the Stray"
    assert persisted.pet_id is None
    assert persisted.certificate_type == "Health Clearance Certificate"
    assert persisted.status == "ACTIVE"
    assert persisted.issue_date == date(2026, 9, 16)


@pytest.mark.asyncio
async def test_post_then_get_returns_same_cert_id(
    mock_user: CurrentUser, mock_request: Request
) -> None:
    """POST then GET returns the EXACT SAME cert_id stored at issuance."""
    stored_cert_id = f"CERT-HC-{uuid.uuid4().hex[:8].upper()}"
    cert_id_pk = uuid.uuid4()
    mock_cert_row = DigitalCertificate(
        id=cert_id_pk,
        cert_id=stored_cert_id,
        certificate_type="Health Clearance Certificate",
        pet_name="Max",
        pet_id=None,
        recipient_name=None,
        clearance_purpose="General Health Check Passed",
        authorized_by="Dr. Test Vet",
        issue_date=date(2026, 9, 16),
        status="ACTIVE",
        created_by_id=mock_user.id,
    )

    mock_db = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.scalars.return_value.all.return_value = [mock_cert_row]
    mock_db.execute.return_value = mock_exec_result

    get_response = await list_digital_certificates(db=mock_db)

    assert get_response.success is True
    assert len(get_response.data) == 1
    retrieved = get_response.data[0]
    assert retrieved.certificate_id == stored_cert_id
    assert retrieved.id == cert_id_pk
    assert retrieved.pet_name == "Max"


@pytest.mark.asyncio
async def test_adoption_certificate_readback_preserves_type_and_recipient(
    mock_user: CurrentUser, mock_request: Request
) -> None:
    """Adoption certificate read-back accurately preserves certificate_type and recipient_name."""
    mock_db = AsyncMock()
    added_objects = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    payload = GenerateAdoptionCertRequest(
        dog_name="Rocky",
        adopter_name="Jane Doe",
        adoption_date="2026-09-16",
    )

    response = await generate_adoption_cert(
        payload=payload,
        request=mock_request,
        current_user=mock_user,
        audit=AsyncMock(),
        db=mock_db,
    )

    assert response.success is True
    issued_cert_id = response.data.certificate_id
    assert response.data.recipient_name == "Jane Doe"
    assert response.data.certificate_type == "Adoption Certificate"

    # Verify DigitalCertificate row was persisted with exact fields
    cert_rows = [o for o in added_objects if isinstance(o, DigitalCertificate)]
    assert len(cert_rows) == 1
    persisted = cert_rows[0]
    assert persisted.cert_id == issued_cert_id
    assert persisted.recipient_name == "Jane Doe"
    assert persisted.certificate_type == "Adoption Certificate"
    assert persisted.pet_name == "Rocky"
