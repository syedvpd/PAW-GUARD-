"""E2E tests for VOLUNTEERS module (15 endpoints)."""
import uuid
import pytest
from datetime import UTC, datetime, timedelta
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestVolunteerEndpoints:
    """All 15 volunteer endpoints."""

    async def test_create_volunteer(self, client, setup):
        r = await call(client, "volunteers", "POST", "/api/v1/volunteers/apply",
                       headers=setup.admin_headers, json={
                           "emergency_contact_name": "Emergency Contact",
                           "emergency_contact_phone": "+1234567890",
                           "skills": "animal care",
                           "availability": "weekends",
                       }, expected=201)
        TEST.volunteer_profile_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_volunteers(self, client, setup):
        r = await call(client, "volunteers", "GET", "/api/v1/volunteers",
                       headers=setup.admin_headers, expected=200)

    async def test_get_volunteer(self, client, setup):
        if TEST.volunteer_profile_id:
            profile_id = str(TEST.volunteer_profile_id)
        else:
            create_r = await client.post("/api/v1/volunteers/apply", json={
                "emergency_contact_name": "Contact",
                "emergency_contact_phone": "+1234567890",
                "skills": "grooming",
                "availability": "daily",
            }, headers=setup.admin_headers)
            profile_id = create_r.json()["data"]["id"]
        r = await call(client, "volunteers", "GET",
                       f"/api/v1/volunteers/{profile_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_update_volunteer(self, client, setup):
        if TEST.volunteer_profile_id:
            profile_id = str(TEST.volunteer_profile_id)
        else:
            create_r = await client.post("/api/v1/volunteers/apply", json={
                "emergency_contact_name": "Update Contact",
                "emergency_contact_phone": "+1234567890",
                "skills": "training",
                "availability": "flexible",
            }, headers=setup.admin_headers)
            profile_id = create_r.json()["data"]["id"]
        r = await call(client, "volunteers", "PUT",
                       f"/api/v1/volunteers/{profile_id}",
                       headers=setup.admin_headers, json={
                           "skills": "animal care, grooming",
                       }, expected=200)

    async def test_delete_volunteer(self, client, setup):
        create_r = await client.post("/api/v1/volunteers/apply", json={
            "emergency_contact_name": "Del Contact",
            "emergency_contact_phone": "+1234567890",
            "skills": "cleaning",
            "availability": "sundays",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            profile_id = create_r.json()["data"]["id"]
            r = await call(client, "volunteers", "DELETE",
                           f"/api/v1/volunteers/{profile_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_create_shift(self, client, setup):
        r = await call(client, "volunteers", "POST", "/api/v1/volunteers/shifts",
                       headers=setup.admin_headers, json={
                           "role_name": "dog_walker",
                           "start_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                           "end_at": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
                           "capacity": 5,
                       }, expected=201)
        TEST.shift_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_shifts(self, client, setup):
        r = await call(client, "volunteers", "GET", "/api/v1/volunteers/shifts",
                       headers=setup.admin_headers, expected=200)

    async def test_join_shift(self, client, setup):
        if TEST.shift_id:
            shift_id = str(TEST.shift_id)
        else:
            create_r = await client.post("/api/v1/volunteers/shifts", json={
                "role_name": "kennel_cleaner",
                "start_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
                "end_at": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
                "capacity": 3,
            }, headers=setup.admin_headers)
            shift_id = create_r.json()["data"]["id"]
        r = await call(client, "volunteers", "POST",
                       f"/api/v1/volunteers/shifts/{shift_id}/join",
                       headers=setup.admin_headers, expected=200)

    async def test_shift_attendance(self, client, setup):
        if TEST.shift_id:
            shift_id = str(TEST.shift_id)
        else:
            create_r = await client.post("/api/v1/volunteers/shifts", json={
                "role_name": "feeder",
                "start_at": (datetime.now(UTC) + timedelta(hours=5)).isoformat(),
                "end_at": (datetime.now(UTC) + timedelta(hours=7)).isoformat(),
                "capacity": 2,
            }, headers=setup.admin_headers)
            shift_id = create_r.json()["data"]["id"]
        r = await call(client, "volunteers", "GET",
                       f"/api/v1/volunteers/shifts/{shift_id}/attendance",
                       headers=setup.admin_headers, expected=200)

    async def test_check_in_attendance(self, client, setup):
        r = await call(client, "volunteers", "POST",
                       "/api/v1/volunteers/attendance/fake-uuid/check-in",
                       headers=setup.admin_headers, expected=404)

    async def test_check_out_attendance(self, client, setup):
        r = await call(client, "volunteers", "POST",
                       "/api/v1/volunteers/attendance/fake-uuid/check-out",
                       headers=setup.admin_headers, expected=404)

    async def test_volunteer_certificate(self, client, setup):
        if TEST.volunteer_profile_id:
            profile_id = str(TEST.volunteer_profile_id)
        else:
            create_r = await client.post("/api/v1/volunteers/apply", json={
                "emergency_contact_name": "Cert Contact",
                "emergency_contact_phone": "+1234567890",
                "skills": "first aid",
                "availability": "any",
            }, headers=setup.admin_headers)
            profile_id = create_r.json()["data"]["id"]
        r = await call(client, "volunteers", "GET",
                       f"/api/v1/volunteers/{profile_id}/certificate",
                       headers=setup.admin_headers, expected=200)

    async def test_volunteer_service_summary(self, client, setup):
        if TEST.volunteer_profile_id:
            profile_id = str(TEST.volunteer_profile_id)
        else:
            create_r = await client.post("/api/v1/volunteers/apply", json={
                "emergency_contact_name": "Sum Contact",
                "emergency_contact_phone": "+1234567890",
                "skills": "all",
                "availability": "full-time",
            }, headers=setup.admin_headers)
            profile_id = create_r.json()["data"]["id"]
        r = await call(client, "volunteers", "GET",
                       f"/api/v1/volunteers/{profile_id}/service-summary",
                       headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_volunteers(self, client, setup):
        create_r = await client.post("/api/v1/volunteers/apply", json={
            "emergency_contact_name": "Bulk Contact",
            "emergency_contact_phone": "+1234567890",
            "skills": "none",
            "availability": "none",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            profile_id = create_r.json()["data"]["id"]
            r = await call(client, "volunteers", "POST",
                           "/api/v1/volunteers/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [profile_id],
                           }, expected=200)

    async def test_bulk_status_volunteers(self, client, setup):
        if TEST.volunteer_profile_id:
            profile_id = str(TEST.volunteer_profile_id)
        else:
            create_r = await client.post("/api/v1/volunteers/apply", json={
                "emergency_contact_name": "Stat Contact",
                "emergency_contact_phone": "+1234567890",
                "skills": "some",
                "availability": "sometimes",
            }, headers=setup.admin_headers)
            profile_id = create_r.json()["data"]["id"]
        r = await call(client, "volunteers", "POST",
                       "/api/v1/volunteers/bulk/status",
                       headers=setup.admin_headers, json={
                           "ids": [profile_id],
                           "status": "active",
                       }, expected=200)
