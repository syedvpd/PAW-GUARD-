"""Integration tests for Dog Management API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Role, User
from pawguard.modules.dog.models import DogStatus

REGISTER_PAYLOAD = {
    "email": "dogapitest@example.com",
    "password": "StrongP@ss99",
    "full_name": "Dog API Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "dogapitest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestDogAPI:
    async def _auth(self, client: AsyncClient, db_session: AsyncSession) -> dict:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == REGISTER_PAYLOAD["email"])
        )
        user = (await db_session.execute(stmt)).scalar_one()
        role_stmt = select(Role).where(Role.name == "super_admin")
        role = (await db_session.execute(role_stmt)).scalar_one()
        user.roles.append(role)
        user.is_verified = True
        await db_session.commit()
        resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        token = resp.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_register_dog(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {
            "name": "Rex",
            "breed": "Labrador",
            "gender": "male",
            "estimated_age": "3 years",
            "weight": 25.5,
            "color": "black",
            "temperament": "friendly",
            "is_adoptable": True,
            "is_quarantine_passed": True,
        }
        resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Rex"
        assert data["status"] == DogStatus.RESCUED.value
        # is_adoptable is always forced False at registration; it can only be
        # granted via the vet-authorized medical clearance endpoint.
        assert data["is_adoptable"] is False

    async def test_register_dog_validation_error(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.post("/api/v1/dogs", json={"name": ""}, headers=headers)
        assert resp.status_code == 422

    async def test_list_dogs(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Buddy", "breed": "Beagle", "gender": "male", "estimated_age": "2y", "weight": 15, "color": "brown", "temperament": "calm"}
        await client.post("/api/v1/dogs", json=payload, headers=headers)
        resp = await client.get("/api/v1/dogs", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "total" in body["meta"]

    async def test_list_dogs_with_filters(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/dogs?status=rescued&is_adoptable=true&breed=Labrador", headers=headers)
        assert resp.status_code == 200

    async def test_get_dog_by_id(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Charlie", "breed": "Pug", "gender": "male", "estimated_age": "1y", "weight": 10, "color": "fawn", "temperament": "playful"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]
        resp = await client.get(f"/api/v1/dogs/{dog_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Charlie"

    async def test_get_dog_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get(f"/api/v1/dogs/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_update_dog(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Max", "breed": "Husky", "gender": "male", "estimated_age": "4y", "weight": 30, "color": "white", "temperament": "energetic"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]
        update_payload = {"name": "Maximus", "weight": 32}
        resp = await client.put(f"/api/v1/dogs/{dog_id}", json=update_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Maximus"
        assert resp.json()["data"]["weight"] == 32

    async def test_patch_dog_status(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Luna", "breed": "Indie", "gender": "female", "estimated_age": "2y", "weight": 18, "color": "brown", "temperament": "shy"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]
        resp = await client.patch(f"/api/v1/dogs/{dog_id}/status", json={"status": "shelter"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == DogStatus.SHELTER.value

    async def test_soft_delete_dog(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Oscar", "breed": "German Shepherd", "gender": "male", "estimated_age": "3y", "weight": 35, "color": "tan", "temperament": "protective"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/dogs/{dog_id}", headers=headers)
        assert resp.status_code == 200
        get_resp = await client.get(f"/api/v1/dogs/{dog_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_bulk_status_update(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload1 = {"name": "Bulk1", "breed": "Mix", "gender": "male", "estimated_age": "1y", "weight": 12, "color": "black", "temperament": "calm"}
        payload2 = {"name": "Bulk2", "breed": "Mix", "gender": "female", "estimated_age": "2y", "weight": 14, "color": "white", "temperament": "calm"}
        d1 = (await client.post("/api/v1/dogs", json=payload1, headers=headers)).json()["data"]
        d2 = (await client.post("/api/v1/dogs", json=payload2, headers=headers)).json()["data"]
        resp = await client.post("/api/v1/dogs/bulk/status-update", json={"ids": [d1["id"], d2["id"]], "status": "clinic"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["updated_count"] == 2

    async def test_bulk_delete(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload1 = {"name": "Del1", "breed": "Mix", "gender": "male", "estimated_age": "1y", "weight": 11, "color": "brown", "temperament": "calm"}
        payload2 = {"name": "Del2", "breed": "Mix", "gender": "female", "estimated_age": "2y", "weight": 13, "color": "black", "temperament": "calm"}
        d1 = (await client.post("/api/v1/dogs", json=payload1, headers=headers)).json()["data"]
        d2 = (await client.post("/api/v1/dogs", json=payload2, headers=headers)).json()["data"]
        resp = await client.post("/api/v1/dogs/bulk/delete", json={"ids": [d1["id"], d2["id"]]}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_count"] == 2
