"""Integration tests for Medical, Surgical & Veterinary API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

REGISTER_PAYLOAD = {
    "email": "medapitest@example.com",
    "password": "StrongP@ss99",
    "full_name": "Medical API Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "medapitest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestMedicalAPI:
    async def _auth(self, client: AsyncClient, db_session: AsyncSession) -> dict:
        return await register_and_auth(
            client, db_session, email=REGISTER_PAYLOAD["email"]
        )

    async def _create_dog(self, client: AsyncClient, headers: dict, name: str = "MedDog") -> str:
        payload = {"name": name, "breed": "Lab", "gender": "male", "estimated_age": "3y", "weight": 22, "color": "golden", "temperament": "friendly", "is_quarantine_passed": True}
        resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        return resp.json()["data"]["id"]

    async def test_create_exam(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "body_condition_score": 5, "triage_diagnosis": "Healthy"}
        resp = await client.post("/api/v1/medical/exams", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["dog_id"] == dog_id
        assert data["triage_diagnosis"] == "Healthy"

    async def test_create_treatment(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "treatment_type": "Surgery", "description": "ACL repair"}
        resp = await client.post("/api/v1/medical/treatments", json=payload, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["treatment_type"] == "Surgery"

    async def test_create_vaccination(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "vaccine_name": "Rabies"}
        resp = await client.post("/api/v1/medical/vaccinations", json=payload, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["vaccine_name"] == "Rabies"

    async def test_create_prescription(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "drug_name": "Amoxicillin", "dosage": "500mg", "route": "oral", "start_at": "2026-07-29T10:00:00Z", "end_at": "2026-08-05T10:00:00Z"}
        resp = await client.post("/api/v1/medical/prescriptions", json=payload, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["drug_name"] == "Amoxicillin"

    async def test_create_exam_validation_error(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.post("/api/v1/medical/exams", json={"dog_id": str(uuid.uuid4())}, headers=headers)
        assert resp.status_code == 422

    async def test_list_exams(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        await client.post("/api/v1/medical/exams", json={"dog_id": dog_id, "body_condition_score": 5, "triage_diagnosis": "Checkup"}, headers=headers)
        resp = await client.get("/api/v1/medical/exams", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    async def test_list_treatments(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/medical/treatments", headers=headers)
        assert resp.status_code == 200

    async def test_list_vaccinations(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/medical/vaccinations", headers=headers)
        assert resp.status_code == 200

    async def test_list_prescriptions(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/medical/prescriptions", headers=headers)
        assert resp.status_code == 200

    async def test_get_medical_history(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        await client.post("/api/v1/medical/exams", json={"dog_id": dog_id, "body_condition_score": 5, "triage_diagnosis": "Annual"}, headers=headers)
        await client.post("/api/v1/medical/vaccinations", json={"dog_id": dog_id, "vaccine_name": "DHPP"}, headers=headers)
        resp = await client.get(f"/api/v1/medical/dogs/{dog_id}/history", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["exams"]) >= 1
        assert len(data["vaccinations"]) >= 1

    async def test_update_prescription(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "drug_name": "Metacam", "dosage": "100mg", "route": "oral", "start_at": "2026-07-29T10:00:00Z", "end_at": "2026-08-05T10:00:00Z"}
        rx = (await client.post("/api/v1/medical/prescriptions", json=payload, headers=headers)).json()["data"]
        update_payload = {"dosage": "150mg"}
        resp = await client.put(f"/api/v1/medical/prescriptions/{rx['id']}", json=update_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["dosage"] == "150mg"

    async def test_patch_prescription_status(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "drug_name": "Cephalexin", "dosage": "250mg", "route": "oral", "start_at": "2026-07-29T10:00:00Z", "end_at": "2026-08-05T10:00:00Z"}
        rx = (await client.post("/api/v1/medical/prescriptions", json=payload, headers=headers)).json()["data"]
        resp = await client.patch(f"/api/v1/medical/prescriptions/{rx['id']}/status", json={"is_active": False}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

    async def test_update_prescription_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.put(f"/api/v1/medical/prescriptions/{uuid.uuid4()}", json={"dosage": "500mg"}, headers=headers)
        assert resp.status_code == 404

    async def test_delete_exam(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        exam = (await client.post("/api/v1/medical/exams", json={"dog_id": dog_id, "body_condition_score": 5, "triage_diagnosis": "Delete test"}, headers=headers)).json()["data"]
        resp = await client.delete(f"/api/v1/medical/exams/{exam['id']}", headers=headers)
        assert resp.status_code == 200

    async def test_delete_treatment(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        treatment = (await client.post("/api/v1/medical/treatments", json={"dog_id": dog_id, "treatment_type": "Wound care", "description": "Cleaning and bandaging"}, headers=headers)).json()["data"]
        resp = await client.delete(f"/api/v1/medical/treatments/{treatment['id']}", headers=headers)
        assert resp.status_code == 200

    async def test_delete_vaccination(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        vac = (await client.post("/api/v1/medical/vaccinations", json={"dog_id": dog_id, "vaccine_name": "Bordetella"}, headers=headers)).json()["data"]
        resp = await client.delete(f"/api/v1/medical/vaccinations/{vac['id']}", headers=headers)
        assert resp.status_code == 200

    async def test_delete_prescription(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        rx = (await client.post("/api/v1/medical/prescriptions", json={"dog_id": dog_id, "drug_name": "Prednisone", "dosage": "10mg", "route": "oral", "start_at": "2026-07-29T10:00:00Z", "end_at": "2026-08-05T10:00:00Z"}, headers=headers)).json()["data"]
        resp = await client.delete(f"/api/v1/medical/prescriptions/{rx['id']}", headers=headers)
        assert resp.status_code == 200

    async def test_delete_unknown_entity_type(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.delete(f"/api/v1/medical/unknown/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False
