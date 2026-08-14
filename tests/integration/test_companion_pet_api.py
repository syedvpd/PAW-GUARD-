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
    return await register_and_auth(client, db_session, email=email, role="general_public")


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

    # 4. Public endpoint without token -> 200 OK
    anon = await client.get(
        f"/api/v1/companion-pets/clinics/{clinic_id}/veterinarians",
    )
    assert anon.status_code == 200, anon.text
    assert len(anon.json()["data"]) == 1


@pytest.mark.asyncio
async def test_appointment_cancellation_endpoints(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Validate appointment cancellation via POST, PATCH, PUT, and DELETE with permissions and ownership."""
    owner_headers = await register_and_auth(
        client, db_session, email="appt-cancel-owner@example.com", role="app_user"
    )
    other_headers = await register_and_auth(
        client, db_session, email="appt-cancel-other@example.com", role="app_user"
    )
    admin_headers = await register_and_auth(
        client, db_session, email="appt-cancel-admin@example.com", role="super_admin"
    )

    # 1. Create a pet and clinic
    pet_res = await client.post(
        "/api/v1/companion-pets",
        json={"name": "Shadow", "species": "dog"},
        headers=owner_headers,
    )
    assert pet_res.status_code == 201, pet_res.text
    pet_id = pet_res.json()["data"]["id"]

    clinic_res = await client.post(
        "/api/v1/companion-pets/clinics",
        json={"name": "City Vet Care", "address": "123 Street", "phone": "+919988776655"},
        headers=admin_headers,
    )
    assert clinic_res.status_code == 201, clinic_res.text
    clinic_id = clinic_res.json()["data"]["id"]

    # 2. Book appointment
    starts_at = datetime.now(UTC) + timedelta(days=5)
    booking = {
        "pet_id": pet_id,
        "clinic_id": clinic_id,
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + timedelta(minutes=30)).isoformat(),
        "reason": "Vaccination checkup",
    }
    appt_res = await client.post(
        "/api/v1/companion-pets/appointments",
        json=booking,
        headers=owner_headers,
    )
    assert appt_res.status_code == 201, appt_res.text
    appt_id = appt_res.json()["data"]["id"]
    assert appt_res.json()["data"]["status"] == "requested"

    # 3. Unauthorized user cannot cancel appointment -> 403
    unauth_cancel = await client.post(
        f"/api/v1/companion-pets/appointments/{appt_id}/cancel",
        json={"reason": "Not my pet"},
        headers=other_headers,
    )
    assert unauth_cancel.status_code == 403, unauth_cancel.text

    # 4. Owner cancels appointment via POST /appointments/{id}/cancel with optional body -> 200 OK
    cancel_res = await client.post(
        f"/api/v1/companion-pets/appointments/{appt_id}/cancel",
        json={"reason": "Scheduling conflict"},
        headers=owner_headers,
    )
    assert cancel_res.status_code == 200, cancel_res.text
    assert cancel_res.json()["data"]["status"] == "cancelled"
    assert cancel_res.json()["data"]["cancellation_reason"] == "Scheduling conflict"

    # 5. Cancelling an already cancelled appointment -> 409 Conflict
    re_cancel = await client.post(
        f"/api/v1/companion-pets/appointments/{appt_id}/cancel",
        json={},
        headers=owner_headers,
    )
    assert re_cancel.status_code == 409, re_cancel.text

    # 6. Book second appointment and cancel via DELETE /appointments/{id}
    starts_at2 = datetime.now(UTC) + timedelta(days=7)
    booking2 = {
        "pet_id": pet_id,
        "clinic_id": clinic_id,
        "starts_at": starts_at2.isoformat(),
        "ends_at": (starts_at2 + timedelta(minutes=30)).isoformat(),
        "reason": "Dental inspection",
    }
    appt_res2 = await client.post(
        "/api/v1/companion-pets/appointments",
        json=booking2,
        headers=owner_headers,
    )
    assert appt_res2.status_code == 201, appt_res2.text
    appt_id2 = appt_res2.json()["data"]["id"]

    delete_cancel = await client.delete(
        f"/api/v1/companion-pets/appointments/{appt_id2}",
        headers=owner_headers,
    )
    assert delete_cancel.status_code == 200, delete_cancel.text
    assert delete_cancel.json()["data"]["status"] == "cancelled"

    # 7. Book third appointment and cancel via PATCH alias without body
    starts_at3 = datetime.now(UTC) + timedelta(days=9)
    booking3 = {
        "pet_id": pet_id,
        "clinic_id": clinic_id,
        "starts_at": starts_at3.isoformat(),
        "ends_at": (starts_at3 + timedelta(minutes=30)).isoformat(),
        "reason": "Ear cleaning",
    }
    appt_res3 = await client.post(
        "/api/v1/companion-pets/appointments",
        json=booking3,
        headers=owner_headers,
    )
    assert appt_res3.status_code == 201, appt_res3.text
    appt_id3 = appt_res3.json()["data"]["id"]

    patch_cancel = await client.patch(
        f"/api/v1/companion-pets/appointments/{appt_id3}/cancel",
        headers=owner_headers,
    )
    assert patch_cancel.status_code == 200, patch_cancel.text
    assert patch_cancel.json()["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_medical_records_and_files_endpoints(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_headers = await _public_owner_auth(client, db_session, "medical-record-owner@example.com")
    other_headers = await _public_owner_auth(client, db_session, "medical-record-other@example.com")

    # 1. Create a pet
    pet_res = await client.post(
        "/api/v1/companion-pets",
        json={"name": "Rocky", "species": "dog"},
        headers=owner_headers,
    )
    assert pet_res.status_code == 201, pet_res.text
    pet_id = pet_res.json()["data"]["id"]

    # 2. Request medical file upload url
    upload_res = await client.post(
        f"/api/v1/companion-pets/{pet_id}/medical-files/upload-url",
        json={"original_filename": "vax.pdf", "mime_type": "application/pdf", "file_size": 1234},
        headers=owner_headers,
    )
    assert upload_res.status_code == 201, upload_res.text
    file_id = upload_res.json()["data"]["file_id"]

    # 3. Confirm upload
    confirm_res = await client.put(
        f"/api/v1/companion-pets/{pet_id}/medical-files/{file_id}/confirm",
        headers=owner_headers,
    )
    assert confirm_res.status_code == 200, confirm_res.text

    # 4. Create medical record using the file
    record_payload = {
        "record_type": "Vaccination",
        "title": "Rabies Shot",
        "notes": "Valid for 3 years",
        "stored_file_id": file_id,
    }
    rec_res = await client.post(
        f"/api/v1/companion-pets/{pet_id}/medical-records",
        json=record_payload,
        headers=owner_headers,
    )
    assert rec_res.status_code == 201, rec_res.text
    record_id = rec_res.json()["data"]["id"]

    # 5. Read medical record (GET /medical-records/{record_id})
    get_res = await client.get(
        f"/api/v1/companion-pets/medical-records/{record_id}",
        headers=owner_headers,
    )
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["data"]["title"] == "Rabies Shot"

    # 6. Read medical record with other headers (should be forbidden)
    get_res_unauth = await client.get(
        f"/api/v1/companion-pets/medical-records/{record_id}",
        headers=other_headers,
    )
    assert get_res_unauth.status_code == 403

    # 7. Update medical record (PUT /medical-records/{record_id})
    update_payload = {
        "title": "Rabies Booster",
        "notes": "Updated booster info",
    }
    update_res = await client.put(
        f"/api/v1/companion-pets/medical-records/{record_id}",
        json=update_payload,
        headers=owner_headers,
    )
    assert update_res.status_code == 200, update_res.text
    assert update_res.json()["data"]["title"] == "Rabies Booster"
    assert update_res.json()["data"]["notes"] == "Updated booster info"

    # 8. Update medical record (PATCH /medical-records/{record_id})
    patch_payload = {
        "notes": "Patched note",
    }
    patch_res = await client.patch(
        f"/api/v1/companion-pets/medical-records/{record_id}",
        json=patch_payload,
        headers=owner_headers,
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["data"]["title"] == "Rabies Booster"  # unchanged
    assert patch_res.json()["data"]["notes"] == "Patched note"

    # 9. Get download URL (GET /medical-files/{file_id}/download-url)
    dl_res = await client.get(
        f"/api/v1/companion-pets/medical-files/{file_id}/download-url",
        headers=owner_headers,
    )
    assert dl_res.status_code == 200, dl_res.text
    assert "download_url" in dl_res.json()["data"]

    # 10. Get download URL with other headers (should be forbidden)
    dl_res_unauth = await client.get(
        f"/api/v1/companion-pets/medical-files/{file_id}/download-url",
        headers=other_headers,
    )
    assert dl_res_unauth.status_code == 403

