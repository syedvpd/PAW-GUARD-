"""Integration tests for public rescue media upload URL endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestPublicRescueUpload:
    async def test_public_rescue_media_upload_url(self, client: AsyncClient) -> None:
        payload = {
            "filename": "emergency_evidence_1.jpg",
            "mime_type": "image/jpeg",
            "file_size": 1048576,
        }
        resp = await client.post("/api/v1/public/rescue/media-upload-url", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "upload_url" in data
        assert "object_key" in data
        assert data["object_key"].startswith("rescue/")

    async def test_rescue_media_upload_url_file_size_exceeded(self, client: AsyncClient) -> None:
        payload = {
            "filename": "huge_video.mp4",
            "mime_type": "video/mp4",
            "file_size": 60000000,
        }
        resp = await client.post("/api/v1/public/rescue/media-upload-url", json=payload)
        assert resp.status_code in (400, 422)
