"""E2E tests for STORAGE module (8 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestStorageEndpoints:
    """All 8 storage endpoints."""

    async def test_upload_url(self, client, setup):
        r = await call(client, "storage", "POST", "/api/v1/storage/upload-url",
                       headers=setup.admin_headers, json={
                           "filename": f"test_{uid()}.jpg",
                           "mime_type": "image/jpeg",
                           "file_size": 1024,
                           "folder": "test",
                       }, expected=200)
        TEST.storage_file_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_files(self, client, setup):
        r = await call(client, "storage", "GET", "/api/v1/storage",
                       headers=setup.admin_headers, expected=200)

    async def test_get_file(self, client, setup):
        if TEST.storage_file_id:
            file_id = str(TEST.storage_file_id)
        else:
            create_r = await client.post("/api/v1/storage/upload-url", json={
                "filename": f"get_{uid()}.pdf",
                "mime_type": "application/pdf",
                "file_size": 2048,
                "folder": "test",
            }, headers=setup.admin_headers)
            file_id = create_r.json()["data"]["id"]
        r = await call(client, "storage", "GET", f"/api/v1/storage/{file_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_get_file_not_found(self, client, setup):
        fake_id = str(uuid.uuid4())
        r = await call(client, "storage", "GET", f"/api/v1/storage/{fake_id}",
                       headers=setup.admin_headers, expected=404)

    async def test_confirm_upload(self, client, setup):
        if TEST.storage_file_id:
            file_id = str(TEST.storage_file_id)
        else:
            create_r = await client.post("/api/v1/storage/upload-url", json={
                "filename": f"conf_{uid()}.png",
                "mime_type": "image/png",
                "file_size": 512,
                "folder": "test",
            }, headers=setup.admin_headers)
            file_id = create_r.json()["data"]["id"]
        r = await call(client, "storage", "PUT",
                       f"/api/v1/storage/{file_id}/confirm",
                       headers=setup.admin_headers, expected=200)

    async def test_get_download_url(self, client, setup):
        if TEST.storage_file_id:
            file_id = str(TEST.storage_file_id)
        else:
            create_r = await client.post("/api/v1/storage/upload-url", json={
                "filename": f"dl_{uid()}.jpg",
                "mime_type": "image/jpeg",
                "file_size": 3072,
                "folder": "test",
            }, headers=setup.admin_headers)
            file_id = create_r.json()["data"]["id"]
        r = await call(client, "storage", "GET",
                       f"/api/v1/storage/{file_id}/download-url",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_file(self, client, setup):
        create_r = await client.post("/api/v1/storage/upload-url", json={
            "filename": f"del_{uid()}.txt",
            "mime_type": "text/plain",
            "file_size": 100,
            "folder": "test",
        }, headers=setup.admin_headers)
        if create_r.status_code == 200:
            file_id = create_r.json()["data"]["id"]
            r = await call(client, "storage", "DELETE",
                           f"/api/v1/storage/{file_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_files(self, client, setup):
        create_r = await client.post("/api/v1/storage/upload-url", json={
            "filename": f"bulk_{uid()}.jpg",
            "mime_type": "image/jpeg",
            "file_size": 4096,
            "folder": "test",
        }, headers=setup.admin_headers)
        if create_r.status_code == 200:
            file_id = create_r.json()["data"]["id"]
            r = await call(client, "storage", "POST", "/api/v1/storage/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [file_id],
                           }, expected=200)

    async def test_entity_files(self, client, setup):
        r = await call(client, "storage", "GET",
                       "/api/v1/storage/entity/dog/00000000-0000-0000-0000-000000000000",
                       headers=setup.admin_headers, expected=200)
