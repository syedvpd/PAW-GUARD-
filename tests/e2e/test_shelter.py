"""E2E tests for SHELTER module (24 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestShelterEndpoints:
    """All 24 shelter endpoints."""

    # ── Facilities ───────────────────────────────────────────────────────

    async def test_create_facility(self, client, setup):
        r = await call(client, "shelter", "POST", "/api/v1/shelter/facilities",
                       headers=setup.admin_headers, json={
                           "name": f"Shelter_{uid()}",
                           "address": "123 Rescue Lane",
                           "phone": "+1234567890",
                           "latitude": 28.6139,
                           "longitude": 77.2090,
                           "total_capacity": 50,
                           "facility_type": "shelter",
                       }, expected=201)
        TEST.facility_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_facilities(self, client, setup):
        r = await call(client, "shelter", "GET", "/api/v1/shelter/facilities",
                       headers=setup.admin_headers, expected=200)

    async def test_get_facility(self, client, setup):
        if TEST.facility_id:
            facility_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/shelter/facilities", json={
                "name": f"Shelter_{uid()}",
                "address": "456 Rescue Lane",
                "phone": "+1234567890",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 30,
                "facility_type": "shelter",
            }, headers=setup.admin_headers)
            facility_id = create_r.json()["data"]["id"]
        r = await call(client, "shelter", "GET",
                       f"/api/v1/shelter/facilities/{facility_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_update_facility(self, client, setup):
        if TEST.facility_id:
            facility_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/shelter/facilities", json={
                "name": f"Shelter_{uid()}",
                "address": "789 Rescue Lane",
                "phone": "+1234567890",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 40,
                "facility_type": "shelter",
            }, headers=setup.admin_headers)
            facility_id = create_r.json()["data"]["id"]
        r = await call(client, "shelter", "PUT",
                       f"/api/v1/shelter/facilities/{facility_id}",
                       headers=setup.admin_headers, json={
                           "total_capacity": 60,
                       }, expected=200)

    async def test_delete_facility(self, client, setup):
        create_r = await client.post("/api/v1/shelter/facilities", json={
            "name": f"DelShelter_{uid()}",
            "address": "Del Shelter Lane",
            "phone": "+1234567890",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "total_capacity": 20,
            "facility_type": "shelter",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            facility_id = create_r.json()["data"]["id"]
            r = await call(client, "shelter", "DELETE",
                           f"/api/v1/shelter/facilities/{facility_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_update_facility_status(self, client, setup):
        if TEST.facility_id:
            facility_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/shelter/facilities", json={
                "name": f"StatShelter_{uid()}",
                "address": "Stat Shelter Lane",
                "phone": "+1234567890",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 25,
                "facility_type": "shelter",
            }, headers=setup.admin_headers)
            facility_id = create_r.json()["data"]["id"]
        r = await call(client, "shelter", "PUT",
                       f"/api/v1/shelter/facilities/{facility_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "active",
                       }, expected=200)

    async def test_bulk_delete_facilities(self, client, setup):
        create_r = await client.post("/api/v1/shelter/facilities", json={
            "name": f"BulkDel_{uid()}",
            "address": "BulkDel Lane",
            "phone": "+1234567890",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "total_capacity": 15,
            "facility_type": "shelter",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            facility_id = create_r.json()["data"]["id"]
            r = await call(client, "shelter", "POST",
                           "/api/v1/shelter/facilities/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [facility_id],
                           }, expected=200)

    async def test_bulk_status_facilities(self, client, setup):
        if TEST.facility_id:
            facility_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/shelter/facilities", json={
                "name": f"BulkStat_{uid()}",
                "address": "BulkStat Lane",
                "phone": "+1234567890",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 35,
                "facility_type": "shelter",
            }, headers=setup.admin_headers)
            facility_id = create_r.json()["data"]["id"]
        r = await call(client, "shelter", "POST",
                       "/api/v1/shelter/facilities/bulk/status",
                       headers=setup.admin_headers, json={
                           "ids": [facility_id],
                           "status": "active",
                       }, expected=200)

    # ── Sections ─────────────────────────────────────────────────────────

    async def test_create_section(self, client, setup):
        if TEST.facility_id:
            facility_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/shelter/facilities", json={
                "name": f"SecShelter_{uid()}",
                "address": "Sec Lane",
                "phone": "+1234567890",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 40,
                "facility_type": "shelter",
            }, headers=setup.admin_headers)
            facility_id = create_r.json()["data"]["id"]
        r = await call(client, "shelter", "POST",
                       f"/api/v1/shelter/facilities/{facility_id}/sections",
                       headers=setup.admin_headers, json={
                           "name": f"Section_{uid()}",
                           "section_type": "general",
                           "capacity": 10,
                       }, expected=201)
        TEST.section_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_sections(self, client, setup):
        if TEST.facility_id:
            facility_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/shelter/facilities", json={
                "name": f"ListSec_{uid()}",
                "address": "ListSec Lane",
                "phone": "+1234567890",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 30,
                "facility_type": "shelter",
            }, headers=setup.admin_headers)
            facility_id = create_r.json()["data"]["id"]
        r = await call(client, "shelter", "GET",
                       f"/api/v1/shelter/facilities/{facility_id}/sections",
                       headers=setup.admin_headers, expected=200)

    # ── Kennels ──────────────────────────────────────────────────────────

    async def test_create_kennel(self, client, setup):
        if TEST.section_id:
            section_id = str(TEST.section_id)
        else:
            create_r = await client.post("/api/v1/shelter/facilities", json={
                "name": f"KennelShelter_{uid()}",
                "address": "Kennel Lane",
                "phone": "+1234567890",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 30,
                "facility_type": "shelter",
            }, headers=setup.admin_headers)
            facility_id = create_r.json()["data"]["id"]
            sec_r = await client.post(f"/api/v1/shelter/facilities/{facility_id}/sections",
                                      json={"name": f"Sec_{uid()}", "section_type": "general", "capacity": 10},
                                      headers=setup.admin_headers)
            section_id = sec_r.json()["data"]["id"]
        r = await call(client, "shelter", "POST",
                       f"/api/v1/shelter/sections/{section_id}/kennels",
                       headers=setup.admin_headers, json={
                           "identifier": f"K-{uid()}",
                           "capacity": 1,
                       }, expected=201)
        TEST.kennel_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_kennels(self, client, setup):
        if TEST.section_id:
            section_id = str(TEST.section_id)
        else:
            section_id = str(uuid.uuid4())
        r = await call(client, "shelter", "GET",
                       f"/api/v1/shelter/sections/{section_id}/kennels",
                       headers=setup.admin_headers, expected=200)

    async def test_assign_dog_to_kennel(self, client, setup):
        if TEST.kennel_id and TEST.dog_ids:
            kennel_id = str(TEST.kennel_id)
            dog_id = str(TEST.dog_ids[0])
            r = await call(client, "shelter", "POST",
                           f"/api/v1/shelter/kennels/{kennel_id}/assign/{dog_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_unassign_dog_from_kennel(self, client, setup):
        if TEST.kennel_id and TEST.dog_ids:
            kennel_id = str(TEST.kennel_id)
            dog_id = str(TEST.dog_ids[0])
            r = await call(client, "shelter", "PATCH",
                           f"/api/v1/shelter/kennels/{kennel_id}/assign/{dog_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_update_kennel_sanitation(self, client, setup):
        if TEST.kennel_id:
            kennel_id = str(TEST.kennel_id)
        else:
            kennel_id = str(uuid.uuid4())
        r = await call(client, "shelter", "PUT",
                       f"/api/v1/shelter/kennels/{kennel_id}/sanitation",
                       headers=setup.admin_headers, json={
                           "status": "clean",
                       }, expected=200)

    async def test_create_cleaning_log(self, client, setup):
        if TEST.kennel_id:
            kennel_id = str(TEST.kennel_id)
        else:
            kennel_id = str(uuid.uuid4())
        r = await call(client, "shelter", "POST",
                       f"/api/v1/shelter/kennels/{kennel_id}/cleaning-logs",
                       headers=setup.admin_headers, json={
                           "cleaned_by": str(setup.admin_user_id) if hasattr(setup, 'admin_user_id') and setup.admin_user_id else str(uuid.uuid4()),
                           "notes": "Morning cleaning",
                       }, expected=201)

    async def test_list_cleaning_logs(self, client, setup):
        if TEST.kennel_id:
            kennel_id = str(TEST.kennel_id)
        else:
            kennel_id = str(uuid.uuid4())
        r = await call(client, "shelter", "GET",
                       f"/api/v1/shelter/kennels/{kennel_id}/cleaning-logs",
                       headers=setup.admin_headers, expected=200)

    # ── Care Logs ────────────────────────────────────────────────────────

    async def test_create_care_log(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "shelter", "POST", "/api/v1/shelter/care-logs",
                       headers=setup.admin_headers, json={
                           "dog_id": dog_id,
                           "care_type": "feeding",
                           "notes": "Fed kibble",
                       }, expected=201)

    async def test_list_dog_care_logs(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "shelter", "GET",
                       f"/api/v1/shelter/dogs/{dog_id}/care-logs",
                       headers=setup.admin_headers, expected=200)

    # ── Transfers ────────────────────────────────────────────────────────

    async def test_create_transfer(self, client, setup):
        dog_id = str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4())
        r = await call(client, "shelter", "POST", "/api/v1/shelter/transfers",
                       headers=setup.admin_headers, json={
                           "dog_id": dog_id,
                           "from_facility_id": str(TEST.facility_id) if TEST.facility_id else str(uuid.uuid4()),
                           "to_facility_id": str(uuid.uuid4()),
                       }, expected=201)
        TEST.transfer_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_transfers(self, client, setup):
        r = await call(client, "shelter", "GET", "/api/v1/shelter/transfers",
                       headers=setup.admin_headers, expected=200)

    async def test_get_transfer(self, client, setup):
        if TEST.transfer_id:
            transfer_id = str(TEST.transfer_id)
        else:
            transfer_id = str(uuid.uuid4())
        r = await call(client, "shelter", "GET",
                       f"/api/v1/shelter/transfers/{transfer_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_confirm_sender_transfer(self, client, setup):
        if TEST.transfer_id:
            transfer_id = str(TEST.transfer_id)
        else:
            transfer_id = str(uuid.uuid4())
        r = await call(client, "shelter", "POST",
                       f"/api/v1/shelter/transfers/{transfer_id}/confirm-sender",
                       headers=setup.admin_headers, expected=200)

    async def test_confirm_receiver_transfer(self, client, setup):
        if TEST.transfer_id:
            transfer_id = str(TEST.transfer_id)
        else:
            transfer_id = str(uuid.uuid4())
        r = await call(client, "shelter", "POST",
                       f"/api/v1/shelter/transfers/{transfer_id}/confirm-receiver",
                       headers=setup.admin_headers, expected=200)
