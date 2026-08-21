"""Integration tests for Lost/Found pet photo upload (presigned S3 flow).

Mirrors the Emergency (rescue) media-upload architecture: authenticated
clients obtain a presigned PUT URL + object key, upload bytes directly to
storage, then submit the object key on report creation. On read the backend
resolves the stored object key into a fresh signed download URL.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

LOST_BASE = "/api/v1/lost-found"
PHOTO_ENDPOINT = f"{LOST_BASE}/photo-upload-url"
LOST_ENDPOINT = f"{LOST_BASE}/lost"
FOUND_ENDPOINT = f"{LOST_BASE}/found"


def _lost_payload(object_key: str | None = None, photo_url: str | None = None) -> dict:
    return {
        "pet_name": f"LostPet_{uuid.uuid4().hex[:8]}",
        "species": "dog",
        "breed": "labrador",
        "color": "golden",
        "location_address": "123 Main St",
        "lost_at": datetime.now(UTC).isoformat(),
        "photo_object_key": object_key,
        "photo_url": photo_url,
    }


def _found_payload(object_key: str | None = None, photo_url: str | None = None) -> dict:
    return {
        "species": "dog",
        "breed_observed": "labrador",
        "color_observed": "golden",
        "location_address": "456 Oak Ave",
        "found_at": datetime.now(UTC).isoformat(),
        "photo_object_key": object_key,
        "photo_url": photo_url,
    }


async def _auth(client: AsyncClient, db_session: AsyncSession) -> dict:
    return await register_and_auth(
        client, db_session, email=f"lfphoto_{uuid.uuid4().hex[:8]}@example.com"
    )


@pytest.mark.asyncio
class TestLostFoundPhotoUploadUrl:
    """Authenticated presigned-upload URL issuance."""

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        resp = await client.post(
            PHOTO_ENDPOINT,
            json={"filename": "buddy.jpg", "mime_type": "image/jpeg", "file_size": 1024},
        )
        assert resp.status_code == 401

    async def test_jpg_accepted(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={"filename": "buddy.jpg", "mime_type": "image/jpeg", "file_size": 1024},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["upload_url"].startswith("http")
        assert data["object_key"].startswith("lost-found/")
        assert data["object_key"].endswith(".jpg")

    async def test_png_accepted(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={"filename": "buddy.png", "mime_type": "image/png", "file_size": 1024},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["object_key"].endswith(".png")

    async def test_webp_accepted(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={"filename": "buddy.webp", "mime_type": "image/webp", "file_size": 1024},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["object_key"].endswith(".webp")

    async def test_invalid_mime_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={"filename": "buddy.gif", "mime_type": "image/gif", "file_size": 1024},
        )
        assert resp.status_code == 422

    async def test_pdf_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={"filename": "doc.pdf", "mime_type": "application/pdf", "file_size": 1024},
        )
        assert resp.status_code == 422

    async def test_oversized_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={
                "filename": "buddy.jpg",
                "mime_type": "image/jpeg",
                "file_size": 60 * 1024 * 1024,
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestLostReportPhotoFlow:
    async def _create_with_photo(
        self, client: AsyncClient, headers: dict, object_key: str | None, photo_url: str | None
    ) -> dict:
        resp = await client.post(
            LOST_ENDPOINT, headers=headers, json=_lost_payload(object_key, photo_url)
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["data"]

    async def test_uploaded_photo_resolves_to_url(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _auth(client, db_session)
        upload = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={"filename": "buddy.jpg", "mime_type": "image/jpeg", "file_size": 1024},
        )
        object_key = upload.json()["data"]["object_key"]

        data = await self._create_with_photo(client, headers, object_key, None)
        report_id = data["id"]
        assert data["photo_object_key"] == object_key
        # Fresh signed download URL is exposed via photo_url, not the raw key.
        assert data["photo_url"] != object_key
        assert "lost-found/" in data["photo_url"]

        # Read again and confirm the URL is freshly resolved (key not leaked).
        get_resp = await client.get(f"{LOST_ENDPOINT}/{report_id}", headers=headers)
        assert get_resp.status_code == 200
        get_data = get_resp.json()["data"]
        assert get_data["photo_object_key"] == object_key
        assert get_data["photo_url"] != object_key
        assert "lost-found/" in get_data["photo_url"]

    async def test_legacy_photo_url_preserved(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _auth(client, db_session)
        legacy = "https://example.com/old-buddy.jpg"
        data = await self._create_with_photo(client, headers, None, legacy)
        assert data["photo_url"] == legacy
        assert data.get("photo_object_key") is None

    async def test_null_photo(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _auth(client, db_session)
        data = await self._create_with_photo(client, headers, None, None)
        assert data["photo_url"] is None

    async def test_object_key_prefix_enforced(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            LOST_ENDPOINT, headers=headers, json=_lost_payload("rescue/evil.jpg", None)
        )
        assert resp.status_code == 422

    async def test_list_returns_resolved_url(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _auth(client, db_session)
        upload = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={"filename": "list.jpg", "mime_type": "image/jpeg", "file_size": 1024},
        )
        object_key = upload.json()["data"]["object_key"]
        await self._create_with_photo(client, headers, object_key, None)

        resp = await client.get(f"{LOST_ENDPOINT}?status=active", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]
        matched = [i for i in items if i.get("photo_object_key") == object_key]
        assert matched, "created report missing from list"
        assert matched[0]["photo_url"] != object_key


@pytest.mark.asyncio
class TestFoundReportPhotoFlow:
    async def _create_with_photo(
        self, client: AsyncClient, headers: dict, object_key: str | None, photo_url: str | None
    ) -> dict:
        resp = await client.post(
            FOUND_ENDPOINT, headers=headers, json=_found_payload(object_key, photo_url)
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["data"]

    async def test_uploaded_photo_resolves_to_url(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _auth(client, db_session)
        upload = await client.post(
            PHOTO_ENDPOINT,
            headers=headers,
            json={"filename": "found.webp", "mime_type": "image/webp", "file_size": 1024},
        )
        object_key = upload.json()["data"]["object_key"]

        data = await self._create_with_photo(client, headers, object_key, None)
        report_id = data["id"]
        assert data["photo_object_key"] == object_key
        assert data["photo_url"] != object_key
        assert "lost-found/" in data["photo_url"]

        get_resp = await client.get(f"{FOUND_ENDPOINT}/{report_id}", headers=headers)
        assert get_resp.status_code == 200
        get_data = get_resp.json()["data"]
        assert get_data["photo_object_key"] == object_key
        assert get_data["photo_url"] != object_key

    async def test_legacy_photo_url_preserved(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _auth(client, db_session)
        legacy = "https://example.com/old-found.jpg"
        data = await self._create_with_photo(client, headers, None, legacy)
        assert data["photo_url"] == legacy

    async def test_object_key_prefix_enforced(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            FOUND_ENDPOINT, headers=headers, json=_found_payload("dogs/x.jpg", None)
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestEmergencyFlowUnchanged:
    """Guard against regressions in the existing Emergency media flow."""

    async def test_rescue_media_upload_url_still_works(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            "/api/v1/rescue/media-upload-url",
            headers=headers,
            json={"filename": "incident.jpg", "mime_type": "image/jpeg", "file_size": 1024},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "upload_url" in data
        assert "object_key" in data
