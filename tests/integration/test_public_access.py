"""Integration tests for the Module 3.1 fixes:

1. Anonymous public directory reads (dog adoption catalog + lost/found listings).
2. PII masking on rescue responses for non-coordinator roles.
3. Rate limits on public mutation endpoints.
4. Portal legal documents, urgent alerts, and transparency stats (public reads
   with draft-hiding + admin CRUD + authorization).
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.auth_helpers import register_and_auth

from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import DogProfile

REGISTER_PAYLOAD = {
    "email": "publictest@example.com",
    "password": "StrongP@ss99",
    "full_name": "Public Access Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "publictest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestPublicAccess:
    async def _auth(self, client: AsyncClient, db_session: AsyncSession) -> dict:
        """Register, promote to super_admin, complete MFA, return auth headers."""
        return await register_and_auth(client, db_session, email=REGISTER_PAYLOAD["email"])

    async def _auth_as_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        role_name: str,
        email: str,
    ) -> dict:
        return await register_and_auth(client, db_session, email=email, role=role_name)

    # ── 1. Anonymous public directory reads ────────────────────────────────

    async def test_anonymous_dog_directory_only_shows_adoptable_masked(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)

        # Adoptable dog (is_adoptable is normally granted only via vet
        # clearance; set it directly here to isolate the directory view).
        payload = {
            "name": "AdoptableRex",
            "breed": "Labrador",
            "gender": "male",
            "estimated_age": "3 years",
            "weight": 25.5,
            "color": "black",
            "temperament": "friendly",
        }
        resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        assert resp.status_code == 201
        adoptable_id = resp.json()["data"]["id"]
        dog = (
            await db_session.execute(select(DogProfile).where(DogProfile.id == adoptable_id))
        ).scalar_one()
        dog.is_adoptable = True
        await db_session.commit()

        # Internal (non-adoptable) dog must not surface publicly.
        payload2 = {
            "name": "InternalDog",
            "breed": "Indie",
            "gender": "female",
            "estimated_age": "2 years",
            "weight": 18.0,
            "color": "brown",
            "temperament": "timid_fearful",
        }
        resp2 = await client.post("/api/v1/dogs", json=payload2, headers=headers)
        internal_id = resp2.json()["data"]["id"]

        # Anonymous listing: 200, only adoptable dogs, internal IDs masked.
        resp = await client.get("/api/v1/dogs")
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["data"]]
        assert "AdoptableRex" in names
        assert "InternalDog" not in names

        adoptable = next(d for d in resp.json()["data"] if d["name"] == "AdoptableRex")
        assert adoptable["microchip_id"] is None
        assert adoptable["rescue_case_id"] is None
        assert adoptable["shelter_facility_id"] is None
        assert adoptable["kennel_id"] is None

        # Anonymous detail of a non-adoptable dog → 404 (must not leak).
        resp = await client.get(f"/api/v1/dogs/{internal_id}")
        assert resp.status_code == 404

    async def test_anonymous_lost_found_listing_masks_reporter(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        lost_payload = {
            "pet_name": "Max",
            "breed": "Beagle Mix",
            "color": "Brown/Black",
            "location_address": "Road No 5, Jubilee Hills",
            "latitude": 17.4285,
            "longitude": 78.4020,
            "lost_at": "2026-07-28T10:00:00Z",
        }
        resp = await client.post("/api/v1/lost-found/lost", json=lost_payload, headers=headers)
        assert resp.status_code == 201

        # Anonymous listing works and masks the reporter email.
        resp = await client.get("/api/v1/lost-found/lost")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        # The list query eager-loads the reporter (selectinload), so the
        # masking assertion below is never silently skipped.
        reporter = data[0]["user"]
        assert reporter is not None
        assert "***" in reporter["email"]
        assert reporter["email"] != REGISTER_PAYLOAD["email"]
        assert "***" in reporter["full_name"]
        assert reporter["full_name"] != "Public Access Tester"
        assert "***" in reporter["phone"]
        assert reporter["phone"] != "+1234567890"

    async def test_found_report_matches_endpoint(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        found_payload = {
            "breed_observed": "Labrador Mix",
            "color_observed": "Golden",
            "location_address": "Road No 8, Banjara Hills",
            "latitude": 17.4170,
            "longitude": 78.4420,
            "found_at": "2026-07-30T14:00:00Z",
        }
        found_resp = await client.post(
            "/api/v1/lost-found/found", json=found_payload, headers=headers
        )
        assert found_resp.status_code == 201
        found_id = found_resp.json()["data"]["id"]

        # Owner can list matches for their found report.
        matches_resp = await client.get(
            f"/api/v1/lost-found/found/{found_id}/matches", headers=headers
        )
        assert matches_resp.status_code == 200
        assert "data" in matches_resp.json()

        # Any authenticated public reader (donor carries public:read) may view
        # matches for transparency, mirroring the lost-report matches gate.
        reader_headers = await self._auth_as_role(
            client, db_session, "donor", "foundreader@example.com"
        )
        reader_resp = await client.get(
            f"/api/v1/lost-found/found/{found_id}/matches", headers=reader_headers
        )
        assert reader_resp.status_code == 200
        assert isinstance(reader_resp.json()["data"], list)

    # ── 2. Rescue PII masking ──────────────────────────────────────────────

    async def test_rescue_reporter_pii_masked_for_field_agent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # rescue_agent holds rescue:read but NOT rescue:verify/dispatch/admin.
        headers = await self._auth_as_role(
            client, db_session, "rescue_agent", "agent@public.test.com"
        )
        report_payload = {
            "reporter_name": "Jane Public",
            "reporter_phone": "+9876543210",
            "location_address": "Street 5, Block B",
            "physical_condition": "Injured",
        }
        r = await client.post("/api/v1/public/rescue/report", json=report_payload)
        assert r.status_code == 201
        case_id = r.json()["data"]["id"]

        resp = await client.get(f"/api/v1/rescue/{case_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reporter_phone"] != "+9876543210"
        assert "****" in data["reporter_phone"]
        assert data["reporter_name"] != "Jane Public"

    async def test_rescue_reporter_pii_unmasked_for_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)  # super_admin
        report_payload = {
            "reporter_name": "Jane Public",
            "reporter_phone": "+9876543210",
            "location_address": "Street 5, Block B",
            "physical_condition": "Injured",
        }
        r = await client.post("/api/v1/public/rescue/report", json=report_payload)
        case_id = r.json()["data"]["id"]

        resp = await client.get(f"/api/v1/rescue/{case_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reporter_phone"] == "+9876543210"
        assert data["reporter_name"] == "Jane Public"

    async def test_rescue_transition_response_pii_masked_for_field_agent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A rescue_agent (rescue:execute only) must not receive unmasked
        reporter PII from the state-transition POST endpoints either - the
        masking policy must hold for every verb, not just GET."""
        admin_headers = await self._auth(client, db_session)
        report_payload = {
            "reporter_name": "Jane Public",
            "reporter_phone": "+9876543210",
            "location_address": "Street 5, Block B",
            "physical_condition": "Injured",
        }
        r = await client.post("/api/v1/public/rescue/report", json=report_payload)
        case_id = r.json()["data"]["id"]

        # Advance the case to DISPATCHED as admin so the agent can act on it.
        await client.post(
            f"/api/v1/rescue/{case_id}/verify",
            json={"status": "verified"},
            headers=admin_headers,
        )
        user_id = (
            (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"])))
            .scalar_one()
            .id
        )
        await client.post(
            f"/api/v1/rescue/{case_id}/dispatch",
            json={"assigned_driver_id": str(user_id), "vehicle_id": "VAN-009"},
            headers=admin_headers,
        )

        agent_headers = await self._auth_as_role(
            client, db_session, "rescue_agent", "agent2@public.test.com"
        )
        resp = await client.post(f"/api/v1/rescue/{case_id}/located", headers=agent_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reporter_phone"] != "+9876543210"
        assert "****" in data["reporter_phone"]
        assert data["reporter_name"] != "Jane Public"

    # ── 3. Rate limits on public mutations ─────────────────────────────────

    async def test_rescue_report_rate_limited(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        payload = {
            "reporter_name": "Spam",
            "reporter_phone": "+1000000",
            "location_address": "Spam Rd",
            "physical_condition": "Injured",
        }
        statuses = []
        for _ in range(6):
            resp = await client.post("/api/v1/rescue/report", json=payload, headers=headers)
            statuses.append(resp.status_code)
        # Limit is 5 per 60s; the 6th request must be rejected.
        assert statuses[:5] == [201] * 5
        assert statuses[5] == 429

    async def test_portal_admin_write_rate_limited(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """All portal CMS write routes share a 30/min per-user budget
        (PRR §6.1): the 31st admin write within the window is rejected."""
        headers = await self._auth(client, db_session)  # super_admin holds system:admin
        payload = {"question": "Rate limit test?", "answer": "Yes."}
        statuses = []
        for _ in range(31):
            resp = await client.post("/api/v1/portal/admin/faq", json=payload, headers=headers)
            statuses.append(resp.status_code)
        # Limit is 30 per 60s; the 31st request must be rejected with 429.
        assert statuses[:30] == [201] * 30
        assert statuses[30] == 429

    # ── 4. Portal legal docs / urgent alerts / transparency ───────────────

    async def test_public_legal_docs_draft_hiding(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Anonymous visitors see only published legal docs; drafts 404."""
        headers = await self._auth(client, db_session)

        published = {
            "slug": "terms-of-service",
            "title": "Terms of Service",
            "body": "1. Acceptance of Terms.",
            "document_type": "terms",
            "status": "published",
        }
        resp = await client.post("/api/v1/portal/admin/legal", json=published, headers=headers)
        assert resp.status_code == 201

        draft = {
            "slug": "privacy-policy",
            "title": "Privacy Policy",
            "body": "We respect your privacy.",
            "document_type": "privacy",
            "status": "draft",
        }
        resp = await client.post("/api/v1/portal/admin/legal", json=draft, headers=headers)
        assert resp.status_code == 201

        # Anonymous list: published only.
        resp = await client.get("/api/v1/portal/legal")
        assert resp.status_code == 200
        slugs = [d["slug"] for d in resp.json()["data"]]
        assert "terms-of-service" in slugs
        assert "privacy-policy" not in slugs

        # Anonymous detail: published 200, draft 404 (no leak).
        resp = await client.get("/api/v1/portal/legal/terms-of-service")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Terms of Service"
        resp = await client.get("/api/v1/portal/legal/privacy-policy")
        assert resp.status_code == 404

    async def test_admin_legal_crud_and_slug_conflict(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        payload = {
            "slug": "adoption-contract",
            "title": "Adoption Contract",
            "body": "Parties agree to the following...",
            "document_type": "adoption",
        }
        resp = await client.post("/api/v1/portal/admin/legal", json=payload, headers=headers)
        assert resp.status_code == 201
        doc_id = resp.json()["data"]["id"]

        # Admin list includes drafts.
        resp = await client.get("/api/v1/portal/admin/legal", headers=headers)
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()["data"]]
        assert doc_id in ids

        # Duplicate slug → 409.
        resp = await client.post("/api/v1/portal/admin/legal", json=payload, headers=headers)
        assert resp.status_code == 409

        # Update to published + rename.
        resp = await client.put(
            f"/api/v1/portal/admin/legal/{doc_id}",
            json={"status": "published", "title": "Adoption Contract v2"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Adoption Contract v2"

        # Published doc is now publicly visible.
        resp = await client.get("/api/v1/portal/legal/adoption-contract")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Adoption Contract v2"

        # Soft delete → public detail 404.
        resp = await client.delete(f"/api/v1/portal/admin/legal/{doc_id}", headers=headers)
        assert resp.status_code == 200
        resp = await client.get("/api/v1/portal/legal/adoption-contract")
        assert resp.status_code == 404

    async def test_legal_admin_requires_system_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A non-admin (no roles) must not be able to write legal docs."""
        payload = {
            "email": "plainuser@public.test.com",
            "password": "StrongP@ss99",
            "full_name": "Plain User",
            "phone": "+1234567890",
        }
        await client.post("/api/v1/auth/register", json=payload)
        stmt = select(User).options(selectinload(User.roles)).where(User.email == payload["email"])
        user = (await db_session.execute(stmt)).scalar_one()
        user.is_verified = True
        await db_session.commit()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": "StrongP@ss99"},
        )
        token = resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        body = {
            "slug": "terms-of-service",
            "title": "Terms",
            "body": "Body",
            "document_type": "terms",
        }
        resp = await client.post("/api/v1/portal/admin/legal", json=body, headers=headers)
        assert resp.status_code == 403

    async def test_public_urgent_alerts_window_filtering(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Only active alerts inside their scheduled window are served."""
        headers = await self._auth(client, db_session)

        now = datetime.now(UTC)
        # Active inside window → visible (window spans today).
        resp = await client.post(
            "/api/v1/portal/admin/urgent-alerts",
            json={
                "title": "Flood Warning",
                "message": "Roads flooded.",
                "severity": "critical",
                "is_active": True,
                "starts_at": (now - timedelta(days=1)).isoformat(),
                "ends_at": (now + timedelta(days=1)).isoformat(),
            },
            headers=headers,
        )
        assert resp.status_code == 201

        # Inactive → hidden.
        resp = await client.post(
            "/api/v1/portal/admin/urgent-alerts",
            json={
                "title": "Inactive Alert",
                "message": "hidden",
                "severity": "info",
                "is_active": False,
            },
            headers=headers,
        )
        assert resp.status_code == 201

        # Expired window → hidden (ended yesterday).
        resp = await client.post(
            "/api/v1/portal/admin/urgent-alerts",
            json={
                "title": "Expired Alert",
                "message": "past",
                "severity": "info",
                "is_active": True,
                "ends_at": (now - timedelta(days=1)).isoformat(),
            },
            headers=headers,
        )
        assert resp.status_code == 201

        resp = await client.get("/api/v1/portal/urgent-alerts")
        assert resp.status_code == 200
        titles = [a["title"] for a in resp.json()["data"]]
        assert "Flood Warning" in titles
        assert "Inactive Alert" not in titles
        assert "Expired Alert" not in titles

    async def test_admin_urgent_alert_crud(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.post(
            "/api/v1/portal/admin/urgent-alerts",
            json={
                "title": "Heat Advisory",
                "message": "Stay hydrated.",
                "severity": "warning",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        alert_id = resp.json()["data"]["id"]

        resp = await client.put(
            f"/api/v1/portal/admin/urgent-alerts/{alert_id}",
            json={"severity": "critical"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["severity"] == "critical"

        resp = await client.delete(
            f"/api/v1/portal/admin/urgent-alerts/{alert_id}", headers=headers
        )
        assert resp.status_code == 200

    async def test_public_transparency_stats(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Anonymous visitors get the impact aggregates with all fields."""
        resp = await client.get("/api/v1/portal/transparency")
        assert resp.status_code == 200
        data = resp.json()["data"]
        for field in (
            "total_funds_raised",
            "total_donations",
            "total_rescues_completed",
            "successful_adoptions",
            "active_volunteers",
            "active_foster_homes",
            "veterinary_partners",
            "dogs_in_care",
        ):
            assert field in data
