"""E2E tests for FOSTERS module (13 endpoints)."""

import uuid

import pytest
from tests.e2e.factories import TEST
from tests.e2e.helpers import call


@pytest.mark.asyncio
class TestFosterEndpoints:
    """All 13 foster endpoints."""

    async def test_create_foster_profile(self, client, setup):
        r = await call(
            client,
            "fosters",
            "POST",
            "/api/v1/fosters/apply",
            headers=setup.admin_headers,
            json={
                "max_capacity": 3,
                "preferences": "dogs",
            },
            expected=201,
        )
        TEST.foster_profile_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_fosters(self, client, setup):
        await call(
            client, "fosters", "GET", "/api/v1/fosters", headers=setup.admin_headers, expected=200
        )

    async def test_update_foster_profile(self, client, setup):
        if TEST.foster_profile_id:
            profile_id = str(TEST.foster_profile_id)
        else:
            create_r = await client.post(
                "/api/v1/fosters/apply",
                json={
                    "max_capacity": 2,
                    "preferences": "cats",
                },
                headers=setup.admin_headers,
            )
            profile_id = create_r.json()["data"]["id"]
        await call(
            client,
            "fosters",
            "PUT",
            f"/api/v1/fosters/{profile_id}",
            headers=setup.admin_headers,
            json={
                "max_capacity": 5,
            },
            expected=200,
        )

    async def test_delete_foster_profile(self, client, setup):
        create_r = await client.post(
            "/api/v1/fosters/apply",
            json={
                "max_capacity": 1,
                "preferences": "small dogs",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            profile_id = create_r.json()["data"]["id"]
            await call(
                client,
                "fosters",
                "DELETE",
                f"/api/v1/fosters/{profile_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_create_placement(self, client, setup):
        if TEST.foster_profile_id:
            profile_id = str(TEST.foster_profile_id)
        else:
            create_r = await client.post(
                "/api/v1/fosters/apply",
                json={
                    "max_capacity": 3,
                    "preferences": "any",
                },
                headers=setup.admin_headers,
            )
            profile_id = create_r.json()["data"]["id"]
        r = await call(
            client,
            "fosters",
            "POST",
            f"/api/v1/fosters/{profile_id}/placements",
            headers=setup.admin_headers,
            json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "notes": "Test placement",
            },
            expected=201,
        )
        TEST.placement_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_placement_progress(self, client, setup):
        placement_id = str(TEST.placement_id) if TEST.placement_id else str(uuid.uuid4())
        await call(
            client,
            "fosters",
            "GET",
            f"/api/v1/fosters/placements/{placement_id}/progress",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_create_placement_progress(self, client, setup):
        placement_id = str(TEST.placement_id) if TEST.placement_id else str(uuid.uuid4())
        await call(
            client,
            "fosters",
            "POST",
            f"/api/v1/fosters/placements/{placement_id}/progress",
            headers=setup.admin_headers,
            json={
                "weight": 15.0,
                "behavior_notes": "Adjusting well",
            },
            expected=200,
        )

    async def test_list_placement_supplies(self, client, setup):
        placement_id = str(TEST.placement_id) if TEST.placement_id else str(uuid.uuid4())
        await call(
            client,
            "fosters",
            "GET",
            f"/api/v1/fosters/placements/{placement_id}/supplies",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_create_placement_supplies(self, client, setup):
        placement_id = str(TEST.placement_id) if TEST.placement_id else str(uuid.uuid4())
        await call(
            client,
            "fosters",
            "POST",
            f"/api/v1/fosters/placements/{placement_id}/supplies",
            headers=setup.admin_headers,
            json={
                "items": [{"name": "Dog food", "quantity": 2}],
            },
            expected=200,
        )

    async def test_return_placement(self, client, setup):
        placement_id = str(TEST.placement_id) if TEST.placement_id else str(uuid.uuid4())
        await call(
            client,
            "fosters",
            "POST",
            f"/api/v1/fosters/placements/{placement_id}/return",
            headers=setup.admin_headers,
            json={
                "reason": "Owner returned",
            },
            expected=200,
        )

    async def test_convert_to_adopt(self, client, setup):
        placement_id = str(TEST.placement_id) if TEST.placement_id else str(uuid.uuid4())
        await call(
            client,
            "fosters",
            "POST",
            f"/api/v1/fosters/placements/{placement_id}/convert-to-adopt",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_delete_foster(self, client, setup):
        create_r = await client.post(
            "/api/v1/fosters/apply",
            json={
                "max_capacity": 1,
                "preferences": "kittens",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            profile_id = create_r.json()["data"]["id"]
            await call(
                client,
                "fosters",
                "DELETE",
                f"/api/v1/fosters/admin/fosters/{profile_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_bulk_delete_fosters(self, client, setup):
        create_r = await client.post(
            "/api/v1/fosters/apply",
            json={
                "max_capacity": 1,
                "preferences": "puppies",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            profile_id = create_r.json()["data"]["id"]
            await call(
                client,
                "fosters",
                "POST",
                "/api/v1/fosters/bulk/delete",
                headers=setup.admin_headers,
                json={
                    "ids": [profile_id],
                },
                expected=200,
            )
