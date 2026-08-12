"""E2E tests for MEDICAL module (21 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestMedicalEndpoints:
    """All 21 medical endpoints."""

    async def test_create_exam(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "POST", "/api/v1/medical/exams",
                       headers=setup.admin_headers, json={
                           "dog_id": dog_id,
                           "exam_type": "routine_checkup",
                           "findings": "Healthy",
                       }, expected=201)
        TEST.exam_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_exams(self, client, setup):
        r = await call(client, "medical", "GET", "/api/v1/medical/exams",
                       headers=setup.admin_headers, expected=200)

    async def test_create_prescription(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "POST", "/api/v1/medical/prescriptions",
                       headers=setup.admin_headers, json={
                           "dog_id": dog_id,
                           "medication_name": "Amoxicillin",
                           "dosage": "250mg",
                           "frequency": "twice_daily",
                           "start_date": "2026-01-01",
                           "end_date": "2026-01-14",
                       }, expected=201)
        TEST.prescription_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_prescriptions(self, client, setup):
        r = await call(client, "medical", "GET", "/api/v1/medical/prescriptions",
                       headers=setup.admin_headers, expected=200)

    async def test_get_prescription(self, client, setup):
        if TEST.prescription_id:
            prescription_id = str(TEST.prescription_id)
        else:
            create_r = await client.post("/api/v1/medical/prescriptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "medication_name": "Ibuprofen",
                "dosage": "100mg",
                "frequency": "once_daily",
                "start_date": "2026-02-01",
                "end_date": "2026-02-07",
            }, headers=setup.admin_headers)
            prescription_id = create_r.json()["data"]["id"]
        r = await call(client, "medical", "GET",
                       f"/api/v1/medical/prescriptions/{prescription_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_update_prescription(self, client, setup):
        if TEST.prescription_id:
            prescription_id = str(TEST.prescription_id)
        else:
            create_r = await client.post("/api/v1/medical/prescriptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "medication_name": "Paracetamol",
                "dosage": "500mg",
                "frequency": "three_times_daily",
                "start_date": "2026-03-01",
                "end_date": "2026-03-10",
            }, headers=setup.admin_headers)
            prescription_id = create_r.json()["data"]["id"]
        r = await call(client, "medical", "PUT",
                       f"/api/v1/medical/prescriptions/{prescription_id}",
                       headers=setup.admin_headers, json={
                           "dosage": "500mg twice daily",
                       }, expected=200)

    async def test_update_prescription_status(self, client, setup):
        if TEST.prescription_id:
            prescription_id = str(TEST.prescription_id)
        else:
            create_r = await client.post("/api/v1/medical/prescriptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "medication_name": "Doxycycline",
                "dosage": "100mg",
                "frequency": "once_daily",
                "start_date": "2026-04-01",
                "end_date": "2026-04-14",
            }, headers=setup.admin_headers)
            prescription_id = create_r.json()["data"]["id"]
        r = await call(client, "medical", "PATCH",
                       f"/api/v1/medical/prescriptions/{prescription_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "completed",
                       }, expected=200)

    async def test_list_prescription_administrations(self, client, setup):
        if TEST.prescription_id:
            prescription_id = str(TEST.prescription_id)
        else:
            prescription_id = str(uuid.uuid4())
        r = await call(client, "medical", "GET",
                       f"/api/v1/medical/prescriptions/{prescription_id}/administrations",
                       headers=setup.admin_headers, expected=200)

    async def test_create_administration(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "POST", "/api/v1/medical/administrations",
                       headers=setup.admin_headers, json={
                           "dog_id": dog_id,
                           "medication_name": "Amoxicillin",
                           "dosage": "250mg",
                           "notes": "Morning dose",
                       }, expected=201)

    async def test_list_dog_administrations(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "GET",
                       f"/api/v1/medical/dogs/{dog_id}/administrations",
                       headers=setup.admin_headers, expected=200)

    async def test_create_treatment(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "POST", "/api/v1/medical/treatments",
                       headers=setup.admin_headers, json={
                           "dog_id": dog_id,
                           "treatment_type": "wound_care",
                           "description": "Cleaned and bandaged wound",
                       }, expected=201)

    async def test_list_treatments(self, client, setup):
        r = await call(client, "medical", "GET", "/api/v1/medical/treatments",
                       headers=setup.admin_headers, expected=200)

    async def test_create_vaccination(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "POST", "/api/v1/medical/vaccinations",
                       headers=setup.admin_headers, json={
                           "dog_id": dog_id,
                           "vaccine_name": "Rabies",
                           "date_administered": "2026-01-15",
                           "next_due_date": "2027-01-15",
                       }, expected=201)

    async def test_list_vaccinations(self, client, setup):
        r = await call(client, "medical", "GET", "/api/v1/medical/vaccinations",
                       headers=setup.admin_headers, expected=200)

    async def test_create_vaccine_protocol(self, client, setup):
        r = await call(client, "medical", "POST", "/api/v1/medical/vaccine-protocols",
                       headers=setup.admin_headers, json={
                           "protocol_name": f"Protocol_{uid()}",
                           "vaccine_name": "DHPPiL",
                           "doses_required": 3,
                           "interval_days": 21,
                       }, expected=201)

    async def test_list_vaccine_protocols(self, client, setup):
        r = await call(client, "medical", "GET", "/api/v1/medical/vaccine-protocols",
                       headers=setup.admin_headers, expected=200)

    async def test_dog_history(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "GET",
                       f"/api/v1/medical/dogs/{dog_id}/history",
                       headers=setup.admin_headers, expected=200)

    async def test_create_clearance(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "POST",
                       f"/api/v1/medical/clearance/{dog_id}",
                       headers=setup.admin_headers, json={
                           "clearance_type": "quarantine",
                           "notes": "Cleared for adoption",
                       }, expected=200)

    async def test_list_clearances(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "medical", "GET",
                       f"/api/v1/medical/clearances/dogs/{dog_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_medical(self, client, setup):
        r = await call(client, "medical", "POST", "/api/v1/medical/bulk/delete",
                       headers=setup.admin_headers, json={
                           "entity_type": "exam",
                           "ids": [str(uuid.uuid4())],
                       }, expected=200)

    async def test_bulk_status_prescriptions(self, client, setup):
        r = await call(client, "medical", "POST",
                       "/api/v1/medical/bulk/prescriptions/status",
                       headers=setup.admin_headers, json={
                           "ids": [str(uuid.uuid4())],
                           "status": "completed",
                       }, expected=200)

    async def test_delete_medical_entity(self, client, setup):
        r = await call(client, "medical", "DELETE",
                       f"/api/v1/medical/exam/{uuid.uuid4()}",
                       headers=setup.admin_headers, expected=200)
