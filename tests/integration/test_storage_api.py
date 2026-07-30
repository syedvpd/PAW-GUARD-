"""Integration tests for Storage API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Role, User

REGISTER_PAYLOAD = {
    "email": "storageapitest@example.com",
    "password": "StrongP@ss99",
    "full_name": "Storage API Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "storageapitest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestStorageAPI:
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

    async def test_request_upload_url(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {
            "original_filename": "test_photo.jpg",
            "mime_type": "image/jpeg",
            "file_size": 102400,
            "folder": "dogs",
        }
        resp = await client.post("/api/v1/storage/upload-url", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "upload_url" in data
        assert "object_key" in data
        assert "file_id" in data

    async def test_request_upload_url_validation_error(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.post("/api/v1/storage/upload-url", json={}, headers=headers)
        assert resp.status_code == 422

    async def test_confirm_upload(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"original_filename": "confirm.jpg", "mime_type": "image/jpeg", "file_size": 204800, "folder": "medical"}
        create_resp = await client.post("/api/v1/storage/upload-url", json=payload, headers=headers)
        file_id = create_resp.json()["data"]["file_id"]
        resp = await client.put(f"/api/v1/storage/{file_id}/confirm", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_uploaded"] is True

    async def test_get_download_url(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"original_filename": "download.pdf", "mime_type": "application/pdf", "file_size": 51200, "folder": "documents"}
        create_resp = await client.post("/api/v1/storage/upload-url", json=payload, headers=headers)
        file_id = create_resp.json()["data"]["file_id"]
        await client.put(f"/api/v1/storage/{file_id}/confirm", headers=headers)
        resp = await client.get(f"/api/v1/storage/{file_id}/download-url", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "download_url" in data
        assert data["file_id"] == file_id

    async def test_get_file(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"original_filename": "file.txt", "mime_type": "text/plain", "file_size": 1000, "folder": "profiles"}
        create_resp = await client.post("/api/v1/storage/upload-url", json=payload, headers=headers)
        file_id = create_resp.json()["data"]["file_id"]
        resp = await client.get(f"/api/v1/storage/{file_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["original_filename"] == "file.txt"

    async def test_get_file_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get(f"/api/v1/storage/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_list_files(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/storage", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    async def test_list_files_with_filters(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/storage?folder=dogs", headers=headers)
        assert resp.status_code == 200

    async def test_delete_file(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"original_filename": "delete_me.txt", "mime_type": "text/plain", "file_size": 500, "folder": "shelters"}
        create_resp = await client.post("/api/v1/storage/upload-url", json=payload, headers=headers)
        file_id = create_resp.json()["data"]["file_id"]
        resp = await client.delete(f"/api/v1/storage/{file_id}", headers=headers)
        assert resp.status_code == 200
        get_resp = await client.get(f"/api/v1/storage/{file_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_download_url_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get(f"/api/v1/storage/{uuid.uuid4()}/download-url", headers=headers)
        assert resp.status_code == 404

    async def test_confirm_upload_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.put(f"/api/v1/storage/{uuid.uuid4()}/confirm", headers=headers)
        assert resp.status_code == 404
