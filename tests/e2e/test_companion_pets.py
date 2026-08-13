"""E2E tests for COMPANION PETS module (27 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestCompanionPetEndpoints:
    """All 27 companion pet endpoints."""

    async def test_create_companion_pet(self, client, setup):
        r = await call(client, "companion_pets", "POST", "/api/v1/companion-pets",
                       headers=setup.admin_headers, json={
                           "name": f"Whiskers_{uid()}",
                           "species": "cat",
                           "breed": "persian",
                           "date_of_birth": "2022-01-15",
                           "gender": "female",
                           "weight": 4.5,
                       }, expected=201)
        TEST.companion_pet_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_companion_pets(self, client, setup):
        r = await call(client, "companion_pets", "GET", "/api/v1/companion-pets",
                       headers=setup.admin_headers, expected=200)

    async def test_get_companion_pet(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"Fido_{uid()}",
                "species": "dog",
                "breed": "labrador",
                "date_of_birth": "2021-06-10",
                "gender": "male",
                "weight": 25.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "GET",
                       f"/api/v1/companion-pets/{pet_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_get_companion_pet_not_found(self, client, setup):
        fake_id = str(uuid.uuid4())
        r = await call(client, "companion_pets", "GET",
                       f"/api/v1/companion-pets/{fake_id}",
                       headers=setup.admin_headers, expected=404)

    async def test_update_companion_pet(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"Max_{uid()}",
                "species": "dog",
                "breed": "beagle",
                "date_of_birth": "2020-03-20",
                "gender": "male",
                "weight": 12.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "PATCH",
                       f"/api/v1/companion-pets/{pet_id}",
                       headers=setup.admin_headers, json={
                           "weight": 13.0,
                       }, expected=200)

    async def test_delete_companion_pet(self, client, setup):
        create_r = await client.post("/api/v1/companion-pets", json={
            "name": f"DelPet_{uid()}",
            "species": "cat",
            "breed": "siamese",
            "date_of_birth": "2023-01-01",
            "gender": "female",
            "weight": 3.5,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            pet_id = create_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "DELETE",
                           f"/api/v1/companion-pets/{pet_id}",
                           headers=setup.admin_headers, expected=200)

    # ── Clinics ──────────────────────────────────────────────────────────

    async def test_list_clinics(self, client, setup):
        r = await call(client, "companion_pets", "GET",
                       "/api/v1/companion-pets/clinics",
                       headers=setup.admin_headers, expected=200)

    async def test_create_clinic(self, client, setup):
        r = await call(client, "companion_pets", "POST",
                       "/api/v1/companion-pets/clinics",
                       headers=setup.admin_headers, json={
                           "name": f"VetClinic_{uid()}",
                           "address": "789 Vet Street",
                           "phone": "+1122334455",
                           "latitude": 28.6139,
                           "longitude": 77.2090,
                       }, expected=201)
        TEST.vet_clinic_id = uuid.UUID(r.json()["data"]["id"])

    async def test_update_clinic(self, client, setup):
        if TEST.vet_clinic_id:
            clinic_id = str(TEST.vet_clinic_id)
        else:
            create_r = await client.post("/api/v1/companion-pets/clinics", json={
                "name": f"VetClinic_{uid()}",
                "address": "101 Vet Ave",
                "phone": "+1122334455",
                "latitude": 28.6139,
                "longitude": 77.2090,
            }, headers=setup.admin_headers)
            clinic_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "PATCH",
                       f"/api/v1/companion-pets/clinics/{clinic_id}",
                       headers=setup.admin_headers, json={
                           "phone": "+9988776655",
                       }, expected=200)

    async def test_delete_clinic(self, client, setup):
        create_r = await client.post("/api/v1/companion-pets/clinics", json={
            "name": f"DelClinic_{uid()}",
            "address": "Del Vet St",
            "phone": "+1122334455",
            "latitude": 28.6139,
            "longitude": 77.2090,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            clinic_id = create_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "DELETE",
                           f"/api/v1/companion-pets/clinics/{clinic_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_create_clinic_membership(self, client, setup):
        if TEST.vet_clinic_id:
            clinic_id = str(TEST.vet_clinic_id)
        else:
            create_r = await client.post("/api/v1/companion-pets/clinics", json={
                "name": f"MemClinic_{uid()}",
                "address": "Mem Vet St",
                "phone": "+1122334455",
                "latitude": 28.6139,
                "longitude": 77.2090,
            }, headers=setup.admin_headers)
            clinic_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "POST",
                       f"/api/v1/companion-pets/clinics/{clinic_id}/memberships",
                       headers=setup.admin_headers, json={
                           "pet_id": str(TEST.companion_pet_id) if TEST.companion_pet_id else str(uuid.uuid4()),
                       }, expected=200)

    # ── Appointments ─────────────────────────────────────────────────────

    async def test_create_appointment(self, client, setup):
        r = await call(client, "companion_pets", "POST",
                       "/api/v1/companion-pets/appointments",
                       headers=setup.admin_headers, json={
                           "pet_id": str(TEST.companion_pet_id) if TEST.companion_pet_id else str(uuid.uuid4()),
                           "clinic_id": str(TEST.vet_clinic_id) if TEST.vet_clinic_id else str(uuid.uuid4()),
                           "appointment_type": "checkup",
                           "scheduled_at": "2026-03-01T10:00:00Z",
                       }, expected=201)
        TEST.appointment_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_appointments(self, client, setup):
        r = await call(client, "companion_pets", "GET",
                       "/api/v1/companion-pets/appointments",
                       headers=setup.admin_headers, expected=200)

    async def test_get_appointment(self, client, setup):
        if TEST.appointment_id:
            appt_id = str(TEST.appointment_id)
        else:
            create_r = await client.post("/api/v1/companion-pets/appointments", json={
                "pet_id": str(TEST.companion_pet_id) if TEST.companion_pet_id else str(uuid.uuid4()),
                "clinic_id": str(TEST.vet_clinic_id) if TEST.vet_clinic_id else str(uuid.uuid4()),
                "appointment_type": "vaccination",
                "scheduled_at": "2026-04-01T10:00:00Z",
            }, headers=setup.admin_headers)
            appt_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "GET",
                       f"/api/v1/companion-pets/appointments/{appt_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_confirm_appointment(self, client, setup):
        create_r = await client.post("/api/v1/companion-pets/appointments", json={
            "pet_id": str(TEST.companion_pet_id) if TEST.companion_pet_id else str(uuid.uuid4()),
            "clinic_id": str(TEST.vet_clinic_id) if TEST.vet_clinic_id else str(uuid.uuid4()),
            "appointment_type": "checkup",
            "scheduled_at": "2026-05-01T10:00:00Z",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            appt_id = create_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "POST",
                           f"/api/v1/companion-pets/appointments/{appt_id}/confirm",
                           headers=setup.admin_headers, expected=200)

    async def test_cancel_appointment(self, client, setup):
        create_r = await client.post("/api/v1/companion-pets/appointments", json={
            "pet_id": str(TEST.companion_pet_id) if TEST.companion_pet_id else str(uuid.uuid4()),
            "clinic_id": str(TEST.vet_clinic_id) if TEST.vet_clinic_id else str(uuid.uuid4()),
            "appointment_type": "grooming",
            "scheduled_at": "2026-06-01T10:00:00Z",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            appt_id = create_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "POST",
                           f"/api/v1/companion-pets/appointments/{appt_id}/cancel",
                           headers=setup.admin_headers, expected=200)

    # ── Medical Records ──────────────────────────────────────────────────

    async def test_create_medical_record(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"MedPet_{uid()}",
                "species": "dog",
                "breed": "poodle",
                "date_of_birth": "2021-01-01",
                "gender": "female",
                "weight": 6.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "POST",
                       f"/api/v1/companion-pets/{pet_id}/medical-records",
                       headers=setup.admin_headers, json={
                           "record_type": "vaccination",
                           "description": "Annual vaccination",
                           "date": "2025-01-15",
                       }, expected=201)

    async def test_list_medical_records(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"MedListPet_{uid()}",
                "species": "cat",
                "breed": "maine_coon",
                "date_of_birth": "2022-06-01",
                "gender": "male",
                "weight": 7.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "GET",
                       f"/api/v1/companion-pets/{pet_id}/medical-records",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_medical_record(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"DelMedPet_{uid()}",
                "species": "dog",
                "breed": "bulldog",
                "date_of_birth": "2020-01-01",
                "gender": "male",
                "weight": 22.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        rec_r = await client.post(f"/api/v1/companion-pets/{pet_id}/medical-records",
                                  json={"record_type": "checkup", "description": "Routine", "date": "2025-01-01"},
                                  headers=setup.admin_headers)
        if rec_r.status_code in (200, 201):
            record_id = rec_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "DELETE",
                           f"/api/v1/companion-pets/medical-records/{record_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_get_medical_record(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"GetMedPet_{uid()}",
                "species": "dog",
                "breed": "poodle",
                "date_of_birth": "2021-02-01",
                "gender": "female",
                "weight": 10.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        rec_r = await client.post(f"/api/v1/companion-pets/{pet_id}/medical-records",
                                  json={"record_type": "vaccination", "title": "Rabies Shot", "notes": "Annual booster"},
                                  headers=setup.admin_headers)
        if rec_r.status_code in (200, 201):
            record_id = rec_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "GET",
                           f"/api/v1/companion-pets/medical-records/{record_id}",
                           headers=setup.admin_headers, expected=200)
            assert r.json()["data"]["title"] == "Rabies Shot"

    async def test_update_medical_record(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"UpMedPet_{uid()}",
                "species": "cat",
                "breed": "persian",
                "date_of_birth": "2020-05-01",
                "gender": "male",
                "weight": 4.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        rec_r = await client.post(f"/api/v1/companion-pets/{pet_id}/medical-records",
                                  json={"record_type": "checkup", "title": "General Exam", "notes": "Healthy"},
                                  headers=setup.admin_headers)
        if rec_r.status_code in (200, 201):
            record_id = rec_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "PATCH",
                           f"/api/v1/companion-pets/medical-records/{record_id}",
                           headers=setup.admin_headers, json={"notes": "Updated notes"}, expected=200)
            assert r.json()["data"]["notes"] == "Updated notes"

    # ── Medical Files ────────────────────────────────────────────────────

    async def test_list_medical_files(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"FilePet_{uid()}",
                "species": "dog",
                "breed": "retriever",
                "date_of_birth": "2021-05-01",
                "gender": "female",
                "weight": 28.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "GET",
                       f"/api/v1/companion-pets/{pet_id}/medical-files",
                       headers=setup.admin_headers, expected=200)

    async def test_upload_medical_file(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"UpFilePet_{uid()}",
                "species": "cat",
                "breed": "ragdoll",
                "date_of_birth": "2023-01-01",
                "gender": "female",
                "weight": 4.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "POST",
                       f"/api/v1/companion-pets/{pet_id}/medical-files/upload-url",
                       headers=setup.admin_headers, json={
                           "filename": f"medical_{uid()}.pdf",
                           "mime_type": "application/pdf",
                       }, expected=200)

    async def test_confirm_medical_file(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"ConfFilePet_{uid()}",
                "species": "dog",
                "breed": "dachshund",
                "date_of_birth": "2022-03-01",
                "gender": "male",
                "weight": 8.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        upload_r = await client.post(f"/api/v1/companion-pets/{pet_id}/medical-files/upload-url",
                                     json={"filename": f"conf_{uid()}.pdf", "mime_type": "application/pdf"},
                                     headers=setup.admin_headers)
        if upload_r.status_code == 200:
            file_id = upload_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "PUT",
                           f"/api/v1/companion-pets/{pet_id}/medical-files/{file_id}/confirm",
                           headers=setup.admin_headers, expected=200)

    # ── Reminders ────────────────────────────────────────────────────────

    async def test_create_reminder(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"RemPet_{uid()}",
                "species": "dog",
                "breed": "shih_tzu",
                "date_of_birth": "2022-08-01",
                "gender": "female",
                "weight": 5.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "POST",
                       f"/api/v1/companion-pets/{pet_id}/reminders",
                       headers=setup.admin_headers, json={
                           "reminder_type": "vaccination",
                           "remind_at": "2026-06-01T09:00:00Z",
                           "message": "Vaccination due",
                       }, expected=201)

    async def test_list_reminders(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"RemListPet_{uid()}",
                "species": "cat",
                "breed": "british_shorthair",
                "date_of_birth": "2021-12-01",
                "gender": "male",
                "weight": 5.5,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "GET",
                       f"/api/v1/companion-pets/{pet_id}/reminders",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_reminder(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"DelRemPet_{uid()}",
                "species": "dog",
                "breed": "chihuahua",
                "date_of_birth": "2023-05-01",
                "gender": "male",
                "weight": 2.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        rem_r = await client.post(f"/api/v1/companion-pets/{pet_id}/reminders",
                                  json={"reminder_type": "checkup", "remind_at": "2026-07-01T09:00:00Z", "message": "Checkup"},
                                  headers=setup.admin_headers)
        if rem_r.status_code in (200, 201):
            reminder_id = rem_r.json()["data"]["id"]
            r = await call(client, "companion_pets", "DELETE",
                           f"/api/v1/companion-pets/{pet_id}/reminders/{reminder_id}",
                           headers=setup.admin_headers, expected=200)

    # ── Safety Tag ───────────────────────────────────────────────────────

    async def test_create_safety_tag(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"TagPet_{uid()}",
                "species": "dog",
                "breed": "labrador",
                "date_of_birth": "2021-01-01",
                "gender": "male",
                "weight": 30.0,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "POST",
                       f"/api/v1/companion-pets/{pet_id}/safety-tag",
                       headers=setup.admin_headers, json={
                           "tag_code": f"TAG-{uid()}",
                       }, expected=200)

    async def test_get_safety_tag(self, client, setup):
        if TEST.companion_pet_id:
            pet_id = str(TEST.companion_pet_id)
        else:
            create_r = await client.post("/api/v1/companion-pets", json={
                "name": f"TagGetPet_{uid()}",
                "species": "cat",
                "breed": "siamese",
                "date_of_birth": "2022-04-01",
                "gender": "female",
                "weight": 3.8,
            }, headers=setup.admin_headers)
            pet_id = create_r.json()["data"]["id"]
        r = await call(client, "companion_pets", "GET",
                       f"/api/v1/companion-pets/{pet_id}/safety-tag",
                       headers=setup.admin_headers, expected=200)

    async def test_scan_safety_tag(self, client, setup):
        r = await call(client, "companion_pets", "POST",
                       "/api/v1/companion-pets/safety-tag/scan",
                       headers=setup.admin_headers, json={
                           "tag_code": f"SCAN-{uid()}",
                       }, expected=200)
