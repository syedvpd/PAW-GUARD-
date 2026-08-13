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


@pytest.mark.asyncio
async def test_app_user_role_companion_pets_listing_and_scoping(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ensure normal app_user gets 200 OK for GET /api/v1/companion-pets and sees only own pets."""
    user1_headers = await register_and_auth(
        client, db_session, email="app-user-1@example.com", role="app_user"
    )
    user2_headers = await register_and_auth(
        client, db_session, email="app-user-2@example.com", role="app_user"
    )

    # 1. User 1 creates a pet
    create_res = await client.post(
        "/api/v1/companion-pets",
        json={"name": "Buddy", "species": "dog", "emergency_notes": "Friendly"},
        headers=user1_headers,
    )
    assert create_res.status_code == 201, create_res.text
    pet1_id = create_res.json()["data"]["id"]

    # 2. User 1 lists pets -> 200 OK, includes Buddy
    list1_res = await client.get("/api/v1/companion-pets", headers=user1_headers)
    assert list1_res.status_code == 200, list1_res.text
    pets1 = list1_res.json()["data"]
    assert any(p["id"] == pet1_id for p in pets1)

    # 3. User 2 lists pets -> 200 OK, does NOT include User 1's pet (scoped)
    list2_res = await client.get("/api/v1/companion-pets", headers=user2_headers)
    assert list2_res.status_code == 200, list2_res.text
    pets2 = list2_res.json()["data"]
    assert not any(p["id"] == pet1_id for p in pets2)


@pytest.mark.asyncio
async def test_veterinarian_dropdown_for_app_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """App User can populate the Book Appointment vet dropdown.

    GET /clinics/{clinic_id}/veterinarians must return active veterinarians
    who are members of the clinic, exposing id/full_name to use as vet_id.
    """
    app_headers = await register_and_auth(
        client, db_session, email="app-vet-dropdown@example.com", role="app_user"
    )
    admin_headers = await register_and_auth(
        client, db_session, email="app-vet-dropdown-admin@example.com", role="super_admin"
    )
    await register_and_auth(
        client, db_session, email="app-vet-dropdown-vet@example.com", role="veterinarian"
    )

    clinic = await client.post(
        "/api/v1/companion-pets/clinics",
        json={
            "name": "Dropdown Vet Clinic",
            "address": "99 Dropdown St",
            "phone": "+1122334455",
        },
        headers=admin_headers,
    )
    assert clinic.status_code == 201, clinic.text
    clinic_id = clinic.json()["data"]["id"]

    vet = (
        await db_session.execute(
            select(User).where(User.email == "app-vet-dropdown-vet@example.com")
        )
    ).scalar_one()
    vet.full_name = "Dr. Dropdown"
    vet.phone = "+919000000000"
    vet.profile_picture_url = "https://cdn.example.com/profile/vet.png"
    await db_session.commit()

    membership = await client.post(
        f"/api/v1/companion-pets/clinics/{clinic_id}/memberships",
        json={"user_id": str(vet.id), "membership_role": "vet"},
        headers=admin_headers,
    )
    assert membership.status_code == 201, membership.text

    # 1. 200 with the active veterinarian (app_user token, required permission appointment:read)
    resp = await client.get(
        f"/api/v1/companion-pets/clinics/{clinic_id}/veterinarians",
        headers=app_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    entry = data[0]
    assert entry["id"] == str(vet.id)
    assert entry["full_name"] == "Dr. Dropdown"
    assert entry["email"] == "app-vet-dropdown-vet@example.com"
    assert entry["phone"] == "+919000000000"
    assert entry["profile_picture_url"] == "https://cdn.example.com/profile/vet.png"

    # 2. Clinic with no active veterinarians -> 200 empty list
    empty_clinic = await client.post(
        "/api/v1/companion-pets/clinics",
        json={"name": "Empty Vet Clinic", "address": "1 Empty St", "phone": "+12000000000"},
        headers=admin_headers,
    )
    assert empty_clinic.status_code == 201, empty_clinic.text
    empty_resp = await client.get(
        f"/api/v1/companion-pets/clinics/{empty_clinic.json()['data']['id']}/veterinarians",
        headers=app_headers,
    )
    assert empty_resp.status_code == 200, empty_resp.text
    assert empty_resp.json()["data"] == []

    # 3. Unknown clinic -> 404
    unknown = await client.get(
        f"/api/v1/companion-pets/clinics/{uuid.uuid4()}/veterinarians",
        headers=app_headers,
    )
    assert unknown.status_code == 404, unknown.text

    # 4. No token -> 401
    anon = await client.get(
        f"/api/v1/companion-pets/clinics/{clinic_id}/veterinarians",
    )
    assert anon.status_code == 401, anon.text

    # 5. Roles lacking appointment:read -> 403
    # register_and_auth APPENDS the target role on top of the default
    # general_public role, so clear all roles first to get a pure rescue_agent.
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "app-vet-dropdown-agent@example.com",
            "password": "StrongP@ss99",
            "full_name": "Field Agent",
        },
    )
    agent = (
        await db_session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == "app-vet-dropdown-agent@example.com")
        )
    ).scalar_one()
    agent.roles.clear()
    await db_session.commit()
    restricted_headers = await promote_and_auth(
        client, db_session, email="app-vet-dropdown-agent@example.com", role="rescue_agent"
    )
    forbidden = await client.get(
        f"/api/v1/companion-pets/clinics/{clinic_id}/veterinarians",
        headers=restricted_headers,
    )
    assert forbidden.status_code == 403, forbidden.text
