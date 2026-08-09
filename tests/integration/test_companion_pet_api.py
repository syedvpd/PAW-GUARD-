"""API coverage for companion-pet scoping, QR privacy, and booking conflicts."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.auth_helpers import promote_and_auth, register_and_auth

from pawguard.modules.auth.models import User
from pawguard.modules.companion_pet.models import SafetyTag


async def _public_owner_auth(
    client: AsyncClient, db_session: AsyncSession, email: str
) -> dict[str, str]:
    """Re-grant the registration role without creating a duplicate association."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongP@ss99", "full_name": "Pet Owner"},
    )
    assert response.status_code == 201, response.text
    user = (
        await db_session.execute(
            select(User).options(selectinload(User.roles)).where(User.email == email)
        )
    ).scalar_one()
    user.roles.clear()
    await db_session.commit()
    return await promote_and_auth(client, db_session, email=email, role="general_public")


@pytest.mark.asyncio
async def test_owner_admin_vet_scoping_qr_privacy_and_appointment_conflict(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_headers = await _public_owner_auth(client, db_session, "companion-owner-api@example.com")
    other_headers = await _public_owner_auth(client, db_session, "companion-other-api@example.com")
    admin_headers = await register_and_auth(
        client, db_session, email="companion-admin-api@example.com", role="super_admin"
    )
    vet_headers = await register_and_auth(
        client, db_session, email="companion-vet-api@example.com", role="veterinarian"
    )

    created = await client.post(
        "/api/v1/companion-pets",
        json={"name": "Milo", "species": "dog", "emergency_notes": "Needs quiet handling."},
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    pet_id = created.json()["data"]["id"]

    assert (
        await client.get(f"/api/v1/companion-pets/{pet_id}", headers=other_headers)
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/companion-pets/{pet_id}", headers=admin_headers)
    ).status_code == 200

    tag_response = await client.post(
        f"/api/v1/companion-pets/{pet_id}/safety-tag", headers=owner_headers
    )
    assert tag_response.status_code == 201, tag_response.text
    raw_token = tag_response.json()["data"]["raw_token"]
    assert raw_token

    scan = await client.post("/api/v1/companion-pets/safety-tag/scan", json={"token": raw_token})
    assert scan.status_code == 200, scan.text
    assert "owner_id" not in scan.json()["data"]
    persisted = (
        await db_session.execute(select(SafetyTag).where(SafetyTag.pet_id == uuid.UUID(pet_id)))
    ).scalar_one()
    assert persisted.token_hash != raw_token
    assert raw_token not in persisted.token_hash

    clinic = await client.post(
        "/api/v1/companion-pets/clinics",
        json={
            "name": "Safe Paws Clinic",
            "address": "1 Main Street",
            "phone": "+123456789",
        },
        headers=admin_headers,
    )
    assert clinic.status_code == 201, clinic.text
    clinic_id = clinic.json()["data"]["id"]
    vet = (
        await db_session.execute(select(User).where(User.email == "companion-vet-api@example.com"))
    ).scalar_one()
    membership = await client.post(
        f"/api/v1/companion-pets/clinics/{clinic_id}/memberships",
        json={"user_id": str(vet.id), "membership_role": "vet"},
        headers=admin_headers,
    )
    assert membership.status_code == 201, membership.text

    starts_at = datetime.now(UTC) + timedelta(days=2)
    booking = {
        "pet_id": pet_id,
        "clinic_id": clinic_id,
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
        "reason": "Annual examination",
    }
    first = await client.post(
        "/api/v1/companion-pets/appointments", json=booking, headers=owner_headers
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/api/v1/companion-pets/appointments", json=booking, headers=owner_headers
    )
    assert second.status_code == 409, second.text

    vet_view = await client.get(f"/api/v1/companion-pets/{pet_id}", headers=vet_headers)
    assert vet_view.status_code == 200, vet_view.text
