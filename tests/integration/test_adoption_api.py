"""Integration tests for Adoption Management API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

from pawguard.modules.adoption.models import AdoptionStatus

REGISTER_PAYLOAD = {
    "email": "adoptapitest@example.com",
    "password": "StrongP@ss99",
    "full_name": "Adopt API Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "adoptapitest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestAdoptionAPI:
    async def _auth(self, client: AsyncClient, db_session: AsyncSession) -> dict:
        import uuid
        unique_email = f"adoptapitest_{uuid.uuid4().hex[:8]}@example.com"
        return await register_and_auth(
            client, db_session, email=unique_email
        )

    async def _create_dog(self, client: AsyncClient, headers: dict) -> str:
        payload = {"name": "AdoptDog", "breed": "Lab", "gender": "male", "estimated_age": "2y", "weight": 20, "color": "black", "temperament": "friendly", "is_adoptable": True, "is_quarantine_passed": True}
        resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = resp.json()["data"]["id"]
        # is_adoptable is forced False at registration; grant vet clearance
        # so downstream adoption-flow tests can apply for this dog.
        await client.post(f"/api/v1/medical/clearance/{dog_id}", headers=headers)
        return dog_id

    async def test_apply_for_adoption(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {
            "dog_id": dog_id,
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": True,
            "household_members_count": 3,
            "pet_care_experience": "10 years owning dogs",
        }
        resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["status"] == AdoptionStatus.SUBMITTED.value
        assert data["dog_id"] == dog_id

    async def test_apply_duplicate_adoption(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {
            "dog_id": dog_id,
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": True,
            "household_members_count": 2,
            "pet_care_experience": "First time owner",
        }
        await client.post("/api/v1/adoptions", json=payload, headers=headers)
        resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
        assert resp.status_code == 409

    async def test_list_adoptions(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {
            "dog_id": dog_id,
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": False,
            "household_members_count": 1,
            "pet_care_experience": "Veterinary assistant",
        }
        await client.post("/api/v1/adoptions", json=payload, headers=headers)
        resp = await client.get("/api/v1/adoptions", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "total" in body["meta"]

    async def test_list_adoptions_with_filters(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/adoptions?status=submitted", headers=headers)
        assert resp.status_code == 200

    async def test_update_adoption(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "residential_status": "rented", "has_landlord_approval": True, "has_yard_fence": False, "household_members_count": 1}
        create_resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
        app_id = create_resp.json()["data"]["id"]
        # Status is a state machine now (submitted -> vetting -> home_check ->
        # approved); walk through the pipeline instead of jumping directly.
        await client.put(f"/api/v1/adoptions/{app_id}", json={"status": "screening"}, headers=headers)
        await client.put(f"/api/v1/adoptions/{app_id}", json={"status": "interview"}, headers=headers)
        await client.put(f"/api/v1/adoptions/{app_id}", json={"status": "home_check"}, headers=headers)
        resp = await client.put(f"/api/v1/adoptions/{app_id}", json={"status": "approved"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == AdoptionStatus.APPROVED.value

    async def test_update_adoption_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.put(f"/api/v1/adoptions/{uuid.uuid4()}", json={"status": "approved"}, headers=headers)
        assert resp.status_code == 404

    async def test_patch_adoption_status(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "residential_status": "owned", "has_landlord_approval": True, "has_yard_fence": True, "household_members_count": 4}
        create_resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
        app_id = create_resp.json()["data"]["id"]
        resp = await client.patch(f"/api/v1/adoptions/{app_id}/status", json={"status": "screening"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == AdoptionStatus.SCREENING.value

    async def test_soft_delete_adoption(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog_id, "residential_status": "owned", "has_landlord_approval": False, "has_yard_fence": False, "household_members_count": 2}
        create_resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
        app_id = create_resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/adoptions/{app_id}", headers=headers)
        assert resp.status_code == 200
        get_resp = await client.get(f"/api/v1/adoptions/{app_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_bulk_status_update(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog1_id = await self._create_dog(client, headers)
        dog2_id = await self._create_dog(client, headers)
        payload = {"dog_id": dog1_id, "residential_status": "owned", "has_landlord_approval": True, "has_yard_fence": True, "household_members_count": 2}
        a1 = (await client.post("/api/v1/adoptions", json=payload, headers=headers)).json()["data"]
        payload["dog_id"] = dog2_id
        a2 = (await client.post("/api/v1/adoptions", json=payload, headers=headers)).json()["data"]
        resp = await client.post("/api/v1/adoptions/bulk/status-update", json={"ids": [a1["id"], a2["id"]], "status": "screening"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["updated_count"] == 2
