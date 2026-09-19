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
        return await register_and_auth(client, db_session, email=unique_email)

    async def _create_dog(
        self, client: AsyncClient, headers: dict, db_session: AsyncSession
    ) -> str:
        payload = {
            "name": f"AdoptDog_{uuid.uuid4().hex[:6]}",
            "breed": "Lab",
            "gender": "male",
            "estimated_age": "2y",
            "weight": 20,
            "color": "black",
            "temperament": "friendly",
            "is_adoptable": True,
            "is_quarantine_passed": True,
        }
        resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = resp.json()["data"]["id"]
        # is_adoptable is forced False at registration; grant vet clearance
        # so downstream adoption-flow tests can apply for this dog. Clearance
        # requires a veterinarian role.
        vet_email = f"vet_{uuid.uuid4().hex[:8]}@example.com"
        vet_headers = await register_and_auth(
            client, db_session, email=vet_email, role="veterinarian"
        )
        await client.post(f"/api/v1/medical/clearance/{dog_id}", headers=vet_headers)
        return dog_id

    async def test_apply_for_adoption(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers, db_session)
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

    async def test_apply_duplicate_adoption(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers, db_session)
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
        dog_id = await self._create_dog(client, headers, db_session)
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

    async def test_list_adoptions_with_filters(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/adoptions?status=submitted", headers=headers)
        assert resp.status_code == 200

    async def test_update_adoption(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers, db_session)
        payload = {
            "dog_id": dog_id,
            "residential_status": "rented",
            "has_landlord_approval": True,
            "has_yard_fence": False,
            "household_members_count": 1,
        }
        create_resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
        app_id = create_resp.json()["data"]["id"]
        await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "screening"}, headers=headers
        )
        for doc_type in ("identity_proof", "landlord_approval"):
            doc_resp = await client.post(
                f"/api/v1/adoptions/{app_id}/documents",
                json={
                    "doc_type": doc_type,
                    "media_key": f"documents/{doc_type}.pdf",
                    "filename": f"{doc_type}.pdf",
                    "mime_type": "application/pdf",
                },
                headers=headers,
            )
            assert doc_resp.status_code == 201
        verify_resp = await client.post(
            f"/api/v1/adoptions/{app_id}/documents/verify", headers=headers
        )
        assert verify_resp.status_code == 200
        interview_resp = await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "interview"}, headers=headers
        )
        assert interview_resp.status_code == 200
        home_check_resp = await client.put(
            f"/api/v1/adoptions/{app_id}",
            json={"status": "home_check", "interview_completed_at": "2026-08-10T15:20:00Z"},
            headers=headers,
        )
        assert home_check_resp.status_code == 200
        resp = await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "approved"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == AdoptionStatus.APPROVED.value

    async def test_update_adoption_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.put(
            f"/api/v1/adoptions/{uuid.uuid4()}", json={"status": "approved"}, headers=headers
        )
        assert resp.status_code == 404

    async def test_patch_adoption_status(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers, db_session)
        payload = {
            "dog_id": dog_id,
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": True,
            "household_members_count": 4,
        }
        create_resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
        app_id = create_resp.json()["data"]["id"]
        resp = await client.patch(
            f"/api/v1/adoptions/{app_id}/status", json={"status": "screening"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == AdoptionStatus.SCREENING.value

    async def test_soft_delete_adoption(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        dog_id = await self._create_dog(client, headers, db_session)
        payload = {
            "dog_id": dog_id,
            "residential_status": "owned",
            "has_landlord_approval": False,
            "has_yard_fence": False,
            "household_members_count": 2,
        }
        create_resp = await client.post("/api/v1/adoptions", json=payload, headers=headers)
        app_id = create_resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/adoptions/{app_id}", headers=headers)
        assert resp.status_code == 200
        get_resp = await client.get(f"/api/v1/adoptions/{app_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_bulk_status_update(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        dog1_id = await self._create_dog(client, headers, db_session)
        dog2_id = await self._create_dog(client, headers, db_session)
        payload = {
            "dog_id": dog1_id,
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": True,
            "household_members_count": 2,
        }
        a1 = (await client.post("/api/v1/adoptions", json=payload, headers=headers)).json()["data"]
        payload["dog_id"] = dog2_id
        a2 = (await client.post("/api/v1/adoptions", json=payload, headers=headers)).json()["data"]
        resp = await client.post(
            "/api/v1/adoptions/bulk/status-update",
            json={"ids": [a1["id"], a2["id"]], "status": "screening"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["updated_count"] == 2

    async def _screening_application(
        self, client: AsyncClient, headers: dict, db_session: AsyncSession, residential: str
    ) -> str:
        dog_id = await self._create_dog(client, headers, db_session)
        create_resp = await client.post(
            "/api/v1/adoptions",
            json={
                "dog_id": dog_id,
                "residential_status": residential,
                "has_landlord_approval": residential == "rented",
                "has_yard_fence": False,
                "household_members_count": 2,
            },
            headers=headers,
        )
        app_id = create_resp.json()["data"]["id"]
        await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "screening"}, headers=headers
        )
        return app_id

    async def _add_document(
        self, client: AsyncClient, headers: dict, app_id: str, doc_type: str
    ) -> dict:
        resp = await client.post(
            f"/api/v1/adoptions/{app_id}/documents",
            json={
                "doc_type": doc_type,
                "media_key": f"documents/{uuid.uuid4().hex}.pdf",
                "filename": f"{doc_type}.pdf",
                "mime_type": "application/pdf",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()["data"]

    async def test_interview_blocked_until_documents_verified(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        app_id = await self._screening_application(client, headers, db_session, "owned")

        blocked = await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "interview"}, headers=headers
        )
        assert blocked.status_code == 422

        no_id = await client.post(f"/api/v1/adoptions/{app_id}/documents/verify", headers=headers)
        assert no_id.status_code == 422

        data = await self._add_document(client, headers, app_id, "identity_proof")
        assert data["applicant_documents"][0]["doc_type"] == "identity_proof"
        assert data["documents_verified_at"] is None

        verified = await client.post(
            f"/api/v1/adoptions/{app_id}/documents/verify", headers=headers
        )
        assert verified.status_code == 200
        assert verified.json()["data"]["documents_verified_at"] is not None

        allowed = await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "interview"}, headers=headers
        )
        assert allowed.status_code == 200

    async def test_rented_home_requires_landlord_approval_document(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        app_id = await self._screening_application(client, headers, db_session, "rented")
        await self._add_document(client, headers, app_id, "identity_proof")

        missing = await client.post(f"/api/v1/adoptions/{app_id}/documents/verify", headers=headers)
        assert missing.status_code == 422

        await self._add_document(client, headers, app_id, "landlord_approval")
        ok = await client.post(f"/api/v1/adoptions/{app_id}/documents/verify", headers=headers)
        assert ok.status_code == 200

    async def test_new_document_resets_verification(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        app_id = await self._screening_application(client, headers, db_session, "owned")
        await self._add_document(client, headers, app_id, "identity_proof")
        await client.post(f"/api/v1/adoptions/{app_id}/documents/verify", headers=headers)

        data = await self._add_document(client, headers, app_id, "pet_medical_record")
        assert data["documents_verified_at"] is None
        assert len(data["applicant_documents"]) == 2

    async def test_document_rejects_bad_key_and_mime(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        app_id = await self._screening_application(client, headers, db_session, "owned")
        base = {"doc_type": "identity_proof", "filename": "id.pdf", "mime_type": "application/pdf"}

        bad_key = await client.post(
            f"/api/v1/adoptions/{app_id}/documents",
            json={**base, "media_key": "../secrets/id.pdf"},
            headers=headers,
        )
        assert bad_key.status_code == 422

        bad_mime = await client.post(
            f"/api/v1/adoptions/{app_id}/documents",
            json={**base, "media_key": "documents/id.exe", "mime_type": "application/x-msdownload"},
            headers=headers,
        )
        assert bad_mime.status_code == 422

    async def test_document_download_unknown_id_is_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        app_id = await self._screening_application(client, headers, db_session, "owned")
        resp = await client.get(
            f"/api/v1/adoptions/{app_id}/documents/{uuid.uuid4()}/download", headers=headers
        )
        assert resp.status_code == 404

    async def test_scores_record_their_type(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        app_id = await self._screening_application(client, headers, db_session, "owned")
        score = {
            "home_environment_score": 8,
            "pet_care_knowledge_score": 7,
            "financial_readiness_score": 9,
            "lifestyle_compatibility_score": 8,
            "recommendation": "approve",
        }
        legacy = await client.post(
            f"/api/v1/adoptions/{app_id}/scores", json=score, headers=headers
        )
        assert legacy.status_code == 201
        assert legacy.json()["data"]["score_type"] == "interview"

        inspection = await client.post(
            f"/api/v1/adoptions/{app_id}/scores",
            json={**score, "score_type": "home_inspection"},
            headers=headers,
        )
        assert inspection.status_code == 201

        listed = await client.get(f"/api/v1/adoptions/{app_id}/scores", headers=headers)
        assert sorted(s["score_type"] for s in listed.json()["data"]) == [
            "home_inspection",
            "interview",
        ]

    async def test_feedback_can_be_filtered_by_adoption(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        app_id = await self._screening_application(client, headers, db_session, "owned")
        other_id = await self._screening_application(client, headers, db_session, "owned")
        for target, rating in ((app_id, 5), (other_id, 2)):
            resp = await client.post(
                "/api/v1/grievance/feedback",
                json={"adoption_application_id": target, "rating": rating},
                headers=headers,
            )
            assert resp.status_code == 201

        resp = await client.get(
            f"/api/v1/grievance/feedback?adoption_application_id={app_id}", headers=headers
        )
        assert resp.status_code == 200
        ratings = [f["rating"] for f in resp.json()["data"]]
        assert ratings == [5]

    async def test_document_can_be_removed_and_resets_verification(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        app_id = await self._screening_application(client, headers, db_session, "owned")
        await self._add_document(client, headers, app_id, "identity_proof")
        data = await self._add_document(client, headers, app_id, "other")
        await client.post(f"/api/v1/adoptions/{app_id}/documents/verify", headers=headers)

        wrong = next(d for d in data["applicant_documents"] if d["doc_type"] == "other")
        resp = await client.delete(
            f"/api/v1/adoptions/{app_id}/documents/{wrong['id']}", headers=headers
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert [d["doc_type"] for d in body["applicant_documents"]] == ["identity_proof"]
        assert body["documents_verified_at"] is None

        missing = await client.delete(
            f"/api/v1/adoptions/{app_id}/documents/{wrong['id']}", headers=headers
        )
        assert missing.status_code == 404
