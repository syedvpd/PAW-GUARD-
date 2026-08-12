"""E2E tests for LOST-FOUND module (18 endpoints)."""
import uuid
import pytest
from datetime import UTC, datetime
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestLostFoundEndpoints:
    """All 18 lost-found endpoints."""

    # ── Lost Reports ─────────────────────────────────────────────────────

    async def test_create_lost_report(self, client, setup):
        r = await call(client, "lost_found", "POST", "/api/v1/lost-found/lost",
                       headers=setup.admin_headers, json={
                           "pet_name": f"LostPet_{uid()}",
                           "species": "dog",
                           "breed": "labrador",
                           "color": "golden",
                           "last_seen_location": "123 Main St",
                           "last_seen_date": datetime.now(UTC).isoformat(),
                           "description": "Friendly golden retriever",
                           "contact_phone": "+9876543210",
                       }, expected=201)
        TEST.lost_report_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_lost_reports(self, client, setup):
        r = await call(client, "lost_found", "GET", "/api/v1/lost-found/lost",
                       headers=setup.admin_headers, expected=200)

    async def test_get_lost_report(self, client, setup):
        if TEST.lost_report_id:
            report_id = str(TEST.lost_report_id)
        else:
            create_r = await client.post("/api/v1/lost-found/lost", json={
                "pet_name": f"LostPet_{uid()}",
                "species": "cat",
                "breed": "persian",
                "color": "white",
                "last_seen_location": "456 Oak Ave",
                "last_seen_date": datetime.now(UTC).isoformat(),
                "description": "White cat with blue eyes",
                "contact_phone": "+9876543210",
            }, headers=setup.admin_headers)
            report_id = create_r.json()["data"]["id"]
        r = await call(client, "lost_found", "GET",
                       f"/api/v1/lost-found/lost/{report_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_lost_report(self, client, setup):
        create_r = await client.post("/api/v1/lost-found/lost", json={
            "pet_name": f"DelLost_{uid()}",
            "species": "dog",
            "breed": "poodle",
            "color": "black",
            "last_seen_location": "Del St",
            "last_seen_date": datetime.now(UTC).isoformat(),
            "description": "Black poodle",
            "contact_phone": "+9876543210",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            report_id = create_r.json()["data"]["id"]
            r = await call(client, "lost_found", "DELETE",
                           f"/api/v1/lost-found/lost/{report_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_broadcast_lost(self, client, setup):
        if TEST.lost_report_id:
            report_id = str(TEST.lost_report_id)
        else:
            create_r = await client.post("/api/v1/lost-found/lost", json={
                "pet_name": f"Broadcast_{uid()}",
                "species": "dog",
                "breed": "beagle",
                "color": "tricolor",
                "last_seen_location": "Broadcast St",
                "last_seen_date": datetime.now(UTC).isoformat(),
                "description": "Beagle puppy",
                "contact_phone": "+9876543210",
            }, headers=setup.admin_headers)
            report_id = create_r.json()["data"]["id"]
        r = await call(client, "lost_found", "POST",
                       f"/api/v1/lost-found/lost/{report_id}/broadcast",
                       headers=setup.admin_headers, expected=200)

    async def test_lost_matches(self, client, setup):
        if TEST.lost_report_id:
            report_id = str(TEST.lost_report_id)
        else:
            report_id = str(uuid.uuid4())
        r = await call(client, "lost_found", "GET",
                       f"/api/v1/lost-found/lost/{report_id}/matches",
                       headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_lost(self, client, setup):
        create_r = await client.post("/api/v1/lost-found/lost", json={
            "pet_name": f"BulkLost_{uid()}",
            "species": "dog",
            "breed": "husky",
            "color": "grey",
            "last_seen_location": "Bulk St",
            "last_seen_date": datetime.now(UTC).isoformat(),
            "description": "Grey husky",
            "contact_phone": "+9876543210",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            report_id = create_r.json()["data"]["id"]
            r = await call(client, "lost_found", "POST",
                           "/api/v1/lost-found/lost/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [report_id],
                           }, expected=200)

    # ── Found Reports ────────────────────────────────────────────────────

    async def test_create_found_report(self, client, setup):
        r = await call(client, "lost_found", "POST", "/api/v1/lost-found/found",
                       headers=setup.admin_headers, json={
                           "species": "dog",
                           "breed": "mixed",
                           "color": "brown",
                           "found_location": "456 Oak Ave",
                           "found_date": datetime.now(UTC).isoformat(),
                           "description": "Stray dog found near park",
                           "contact_phone": "+9876543211",
                       }, expected=201)
        TEST.found_report_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_found_reports(self, client, setup):
        r = await call(client, "lost_found", "GET", "/api/v1/lost-found/found",
                       headers=setup.admin_headers, expected=200)

    async def test_get_found_report(self, client, setup):
        if TEST.found_report_id:
            report_id = str(TEST.found_report_id)
        else:
            create_r = await client.post("/api/v1/lost-found/found", json={
                "species": "cat",
                "breed": "tabby",
                "color": "orange",
                "found_location": "789 Elm St",
                "found_date": datetime.now(UTC).isoformat(),
                "description": "Orange tabby cat",
                "contact_phone": "+9876543211",
            }, headers=setup.admin_headers)
            report_id = create_r.json()["data"]["id"]
        r = await call(client, "lost_found", "GET",
                       f"/api/v1/lost-found/found/{report_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_found_report(self, client, setup):
        create_r = await client.post("/api/v1/lost-found/found", json={
            "species": "dog",
            "breed": "terrier",
            "color": "white",
            "found_location": "Del Found St",
            "found_date": datetime.now(UTC).isoformat(),
            "description": "White terrier",
            "contact_phone": "+9876543211",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            report_id = create_r.json()["data"]["id"]
            r = await call(client, "lost_found", "DELETE",
                           f"/api/v1/lost-found/found/{report_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_found_matches(self, client, setup):
        if TEST.found_report_id:
            report_id = str(TEST.found_report_id)
        else:
            report_id = str(uuid.uuid4())
        r = await call(client, "lost_found", "GET",
                       f"/api/v1/lost-found/found/{report_id}/matches",
                       headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_found(self, client, setup):
        create_r = await client.post("/api/v1/lost-found/found", json={
            "species": "dog",
            "breed": "corgi",
            "color": "red",
            "found_location": "Bulk Found St",
            "found_date": datetime.now(UTC).isoformat(),
            "description": "Red corgi",
            "contact_phone": "+9876543211",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            report_id = create_r.json()["data"]["id"]
            r = await call(client, "lost_found", "POST",
                           "/api/v1/lost-found/found/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [report_id],
                           }, expected=200)

    # ── Matches ──────────────────────────────────────────────────────────

    async def test_claim_match(self, client, setup):
        match_id = str(uuid.uuid4())
        r = await call(client, "lost_found", "POST",
                       f"/api/v1/lost-found/matches/{match_id}/claim",
                       headers=setup.admin_headers, json={
                           "claimed_by": str(setup.admin_user_id) if hasattr(setup, 'admin_user_id') and setup.admin_user_id else str(uuid.uuid4()),
                       }, expected=200)

    async def test_review_claim(self, client, setup):
        match_id = str(uuid.uuid4())
        r = await call(client, "lost_found", "POST",
                       f"/api/v1/lost-found/matches/{match_id}/claim/review",
                       headers=setup.admin_headers, json={
                           "approved": True,
                       }, expected=200)

    async def test_resolve_match(self, client, setup):
        match_id = str(uuid.uuid4())
        r = await call(client, "lost_found", "POST",
                       f"/api/v1/lost-found/matches/{match_id}/resolve",
                       headers=setup.admin_headers, expected=200)

    async def test_reunion_stories(self, client, setup):
        r = await call(client, "lost_found", "GET",
                       "/api/v1/lost-found/reunion-stories",
                       headers=setup.admin_headers, expected=200)

    async def test_stories(self, client, setup):
        r = await call(client, "lost_found", "GET",
                       "/api/v1/lost-found/stories",
                       headers=setup.admin_headers, expected=200)
