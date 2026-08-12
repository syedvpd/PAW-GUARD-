"""E2E tests for DOGS module (13 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestDogEndpoints:
    """All 13 dog endpoints."""

    async def test_create_dog(self, client, setup):
        r = await call(client, "dogs", "POST", "/api/v1/dogs",
                       headers=setup.admin_headers, json={
                           "name": f"Buddy_{uid()}",
                           "breed": "indie_mix",
                           "gender": "male",
                           "age_months": 24,
                           "weight": 15.0,
                           "color": "brown",
                           "temperament": "friendly",
                           "is_adoptable": True,
                           "is_quarantine_passed": True,
                       }, expected=201)
        TEST.dog_ids.append(uuid.UUID(r.json()["data"]["id"]))

    async def test_list_dogs(self, client, setup):
        r = await call(client, "dogs", "GET", "/api/v1/dogs",
                       headers=setup.admin_headers, expected=200)

    async def test_get_dog(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"Buddy_{uid()}",
                "breed": "indie_mix",
                "gender": "male",
                "age_months": 24,
                "weight": 15.0,
                "color": "brown",
                "temperament": "friendly",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "GET", f"/api/v1/dogs/{dog_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_get_dog_not_found(self, client, setup):
        fake_id = str(uuid.uuid4())
        r = await call(client, "dogs", "GET", f"/api/v1/dogs/{fake_id}",
                       headers=setup.admin_headers, expected=404)

    async def test_update_dog(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"Buddy_{uid()}",
                "breed": "indie_mix",
                "gender": "male",
                "age_months": 24,
                "weight": 15.0,
                "color": "brown",
                "temperament": "friendly",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "PUT", f"/api/v1/dogs/{dog_id}",
                       headers=setup.admin_headers, json={
                           "name": "UpdatedBuddy",
                           "weight": 16.0,
                       }, expected=200)

    async def test_delete_dog(self, client, setup):
        create_r = await client.post("/api/v1/dogs", json={
            "name": f"DelDog_{uid()}",
            "breed": "labrador",
            "gender": "female",
            "age_months": 12,
            "weight": 10.0,
            "color": "black",
            "temperament": "calm",
            "is_adoptable": True,
            "is_quarantine_passed": True,
        }, headers=setup.admin_headers)
        if create_r.status_code == 201:
            dog_id = create_r.json()["data"]["id"]
            r = await call(client, "dogs", "DELETE", f"/api/v1/dogs/{dog_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_update_dog_status(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"StatusDog_{uid()}",
                "breed": "poodle",
                "gender": "male",
                "age_months": 18,
                "weight": 8.0,
                "color": "white",
                "temperament": "playful",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "PATCH", f"/api/v1/dogs/{dog_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "available",
                       }, expected=200)

    async def test_admin_get_dog(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"AdminDog_{uid()}",
                "breed": "german_shepherd",
                "gender": "male",
                "age_months": 36,
                "weight": 30.0,
                "color": "black",
                "temperament": "alert",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "GET", f"/api/v1/dogs/admin/dogs/{dog_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_admin_update_dog_status(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"AdminStatusDog_{uid()}",
                "breed": "beagle",
                "gender": "female",
                "age_months": 10,
                "weight": 12.0,
                "color": "tricolor",
                "temperament": "curious",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "PATCH",
                       f"/api/v1/dogs/admin/dogs/{dog_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "adopted",
                       }, expected=200)

    async def test_dog_timeline(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"TimelineDog_{uid()}",
                "breed": "golden_retriever",
                "gender": "male",
                "age_months": 24,
                "weight": 28.0,
                "color": "golden",
                "temperament": "gentle",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "GET", f"/api/v1/dogs/{dog_id}/timeline",
                       headers=setup.admin_headers, expected=200)

    async def test_add_weight(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"WeightDog_{uid()}",
                "breed": "labrador",
                "gender": "female",
                "age_months": 30,
                "weight": 25.0,
                "color": "yellow",
                "temperament": "calm",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "POST", f"/api/v1/dogs/{dog_id}/weight",
                       headers=setup.admin_headers, json={
                           "weight": 22.5,
                           "recorded_at": "2025-01-15T10:00:00Z",
                       }, expected=200)

    async def test_list_weights(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"ListWeightDog_{uid()}",
                "breed": "bulldog",
                "gender": "male",
                "age_months": 20,
                "weight": 20.0,
                "color": "fawn",
                "temperament": "stubborn",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "GET", f"/api/v1/dogs/{dog_id}/weights",
                       headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_dogs(self, client, setup):
        create_r = await client.post("/api/v1/dogs", json={
            "name": f"BulkDel_{uid()}",
            "breed": "pug",
            "gender": "male",
            "age_months": 8,
            "weight": 6.0,
            "color": "fawn",
            "temperament": "playful",
            "is_adoptable": True,
            "is_quarantine_passed": True,
        }, headers=setup.admin_headers)
        if create_r.status_code == 201:
            dog_id = create_r.json()["data"]["id"]
            r = await call(client, "dogs", "POST", "/api/v1/dogs/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [dog_id],
                           }, expected=200)

    async def test_bulk_status_update_dogs(self, client, setup):
        if TEST.dog_ids:
            dog_id = str(TEST.dog_ids[0])
        else:
            create_r = await client.post("/api/v1/dogs", json={
                "name": f"BulkStatus_{uid()}",
                "breed": "husky",
                "gender": "female",
                "age_months": 18,
                "weight": 18.0,
                "color": "white",
                "temperament": "energetic",
                "is_adoptable": True,
                "is_quarantine_passed": True,
            }, headers=setup.admin_headers)
            dog_id = create_r.json()["data"]["id"]
        r = await call(client, "dogs", "POST", "/api/v1/dogs/bulk/status-update",
                       headers=setup.admin_headers, json={
                           "ids": [dog_id],
                           "status": "available",
                       }, expected=200)
