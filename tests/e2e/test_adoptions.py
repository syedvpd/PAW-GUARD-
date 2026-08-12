"""E2E tests for ADOPTIONS module (18 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestAdoptionEndpoints:
    """All 18 adoption endpoints."""

    async def test_create_adoption(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "adoptions", "POST", "/api/v1/adoptions",
                       headers=setup.admin_headers, json={
                           "dog_id": dog_id,
                           "residential_status": "owned",
                           "has_landlord_approval": True,
                           "has_yard_fence": True,
                           "household_members_count": 3,
                           "pet_care_experience": "5 years",
                       }, expected=201)
        TEST.adoption_app_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_adoptions(self, client, setup):
        r = await call(client, "adoptions", "GET", "/api/v1/adoptions",
                       headers=setup.admin_headers, expected=200)

    async def test_my_adoptions(self, client, setup):
        r = await call(client, "adoptions", "GET", "/api/v1/adoptions/my",
                       headers=setup.admin_headers, expected=200)

    async def test_get_adoption(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "rented",
                "has_landlord_approval": True,
                "has_yard_fence": False,
                "household_members_count": 2,
                "pet_care_experience": "2 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "GET", f"/api/v1/adoptions/{app_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_get_adoption_not_found(self, client, setup):
        fake_id = str(uuid.uuid4())
        r = await call(client, "adoptions", "GET", f"/api/v1/adoptions/{fake_id}",
                       headers=setup.admin_headers, expected=404)

    async def test_update_adoption(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 4,
                "pet_care_experience": "3 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "PUT", f"/api/v1/adoptions/{app_id}",
                       headers=setup.admin_headers, json={
                           "household_members_count": 5,
                       }, expected=200)

    async def test_delete_adoption(self, client, setup):
        create_r = await client.post("/api/v1/adoptions", json={
            "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": True,
            "household_members_count": 2,
            "pet_care_experience": "1 year",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            app_id = create_r.json()["data"]["id"]
            r = await call(client, "adoptions", "DELETE",
                           f"/api/v1/adoptions/{app_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_update_adoption_status(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 3,
                "pet_care_experience": "4 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "PATCH",
                       f"/api/v1/adoptions/{app_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "approved",
                       }, expected=200)

    async def test_get_adoption_agreement(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 3,
                "pet_care_experience": "5 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "GET",
                       f"/api/v1/adoptions/{app_id}/agreement",
                       headers=setup.admin_headers, expected=200)

    async def test_update_adoption_fee(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 3,
                "pet_care_experience": "2 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "PUT",
                       f"/api/v1/adoptions/{app_id}/fee",
                       headers=setup.admin_headers, json={
                           "adoption_fee": 500.0,
                       }, expected=200)

    async def test_create_follow_up(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 3,
                "pet_care_experience": "3 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "POST",
                       f"/api/v1/adoptions/{app_id}/follow-ups",
                       headers=setup.admin_headers, json={
                           "follow_up_type": "home_visit",
                           "notes": "First follow-up",
                       }, expected=201)

    async def test_list_follow_ups(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 2,
                "pet_care_experience": "1 year",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "GET",
                       f"/api/v1/adoptions/{app_id}/follow-ups",
                       headers=setup.admin_headers, expected=200)

    async def test_submit_follow_up_proof(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 3,
                "pet_care_experience": "2 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        fu_r = await client.post(f"/api/v1/adoptions/{app_id}/follow-ups",
                                 json={"follow_up_type": "phone_call", "notes": "Check-in"},
                                 headers=setup.admin_headers)
        if fu_r.status_code in (200, 201):
            follow_up_id = fu_r.json()["data"]["id"]
            r = await call(client, "adoptions", "POST",
                           f"/api/v1/adoptions/{app_id}/follow-ups/{follow_up_id}/proof",
                           headers=setup.admin_headers, json={
                               "proof_url": "http://example.com/proof.jpg",
                               "notes": "Photo proof",
                           }, expected=200)

    async def test_create_adoption_score(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 4,
                "pet_care_experience": "6 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "POST",
                       f"/api/v1/adoptions/{app_id}/scores",
                       headers=setup.admin_headers, json={
                           "criteria": "home_environment",
                           "score": 85,
                       }, expected=200)

    async def test_get_adoption_scores(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 3,
                "pet_care_experience": "4 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "GET",
                       f"/api/v1/adoptions/{app_id}/scores",
                       headers=setup.admin_headers, expected=200)

    async def test_nearby_shelters(self, client, setup):
        r = await call(client, "adoptions", "GET",
                       "/api/v1/adoptions/nearby-shelters",
                       headers=setup.admin_headers, params={
                           "latitude": 28.6139,
                           "longitude": 77.2090,
                       }, expected=200)

    async def test_admin_delete_adoption(self, client, setup):
        create_r = await client.post("/api/v1/adoptions", json={
            "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": True,
            "household_members_count": 2,
            "pet_care_experience": "1 year",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            app_id = create_r.json()["data"]["id"]
            r = await call(client, "adoptions", "DELETE",
                           f"/api/v1/adoptions/admin/adoptions/{app_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_adoptions(self, client, setup):
        create_r = await client.post("/api/v1/adoptions", json={
            "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": True,
            "household_members_count": 2,
            "pet_care_experience": "1 year",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            app_id = create_r.json()["data"]["id"]
            r = await call(client, "adoptions", "POST",
                           "/api/v1/adoptions/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [app_id],
                           }, expected=200)

    async def test_bulk_status_update_adoptions(self, client, setup):
        if TEST.adoption_app_id:
            app_id = str(TEST.adoption_app_id)
        else:
            create_r = await client.post("/api/v1/adoptions", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "residential_status": "owned",
                "has_landlord_approval": True,
                "has_yard_fence": True,
                "household_members_count": 3,
                "pet_care_experience": "3 years",
            }, headers=setup.admin_headers)
            app_id = create_r.json()["data"]["id"]
        r = await call(client, "adoptions", "POST",
                       "/api/v1/adoptions/bulk/status-update",
                       headers=setup.admin_headers, json={
                           "ids": [app_id],
                           "status": "approved",
                       }, expected=200)
