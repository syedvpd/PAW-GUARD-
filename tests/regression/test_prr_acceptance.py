"""End-to-end regression tests for PRR acceptance criteria."""

import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy import select
from pawguard.modules.rescue.models import RescueRequest, RescueStatus
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.medical.models import MedicalClearance
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus


@pytest.mark.regression
class TestRescueToDogProfile:
    async def test_rescue_lifecycle_creates_dog_profile(self, async_client: AsyncClient, db_session):
        submit_resp = await async_client.post("/api/v1/public/rescue/report", json={
            "reporter_name": "Test Reporter", "reporter_phone": "+919876543210",
            "reporter_email": "reporter@test.com", "location": {"address": "Test St", "latitude": 17.4, "longitude": 78.4},
            "number_of_dogs": 1, "animal_condition": "critical", "description": "Injured dog"
        })
        assert submit_resp.status_code == 201
        rescue_id = submit_resp.json()["data"]["id"]

        verify_resp = await async_client.put(f"/api/v1/rescue/{rescue_id}/status", json={"status": "verified"})
        assert verify_resp.status_code == 200
        dispatch_resp = await async_client.put(f"/api/v1/rescue/{rescue_id}/status", json={"status": "dispatched"})
        assert dispatch_resp.status_code == 200
        locate_resp = await async_client.put(f"/api/v1/rescue/{rescue_id}/status", json={"status": "located"})
        assert locate_resp.status_code == 200
        rescue_resp = await async_client.put(f"/api/v1/rescue/{rescue_id}/status", json={"status": "rescued"})
        assert rescue_resp.status_code == 200
        admit_resp = await async_client.put(f"/api/v1/rescue/{rescue_id}/status", json={"status": "admitted", "facility_id": "facility-uuid"})
        assert admit_resp.status_code == 200

        result = await db_session.execute(select(DogProfile).where(DogProfile.rescue_case_id == rescue_id))
        dog = result.scalar_one_or_none()
        assert dog is not None, "Dog Master Profile not auto-created after ADMITTED"


@pytest.mark.regression
class TestAdoptionExclusivity:
    async def test_concurrent_adoption_approvals_blocked(self, async_client: AsyncClient, db_session, dog_profile, adopter_users):
        app1_resp = await async_client.post("/api/v1/adoption/applications", json={"dog_id": str(dog_profile.id), "applicant_id": str(adopter_users[0].id)})
        app2_resp = await async_client.post("/api/v1/adoption/applications", json={"dog_id": str(dog_profile.id), "applicant_id": str(adopter_users[1].id)})
        app1_id = app1_resp.json()["data"]["id"]
        app2_id = app2_resp.json()["data"]["id"]

        async def approve(app_id):
            return await async_client.put(f"/api/v1/adoption/applications/{app_id}/status", json={"status": "home_check_approved"})

        results = await asyncio.gather(approve(app1_id), approve(app2_id))
        successes = [r for r in results if r.status_code == 200]
        assert len(successes) == 1, "Zero Exclusivity Violation: both applications approved concurrently"


@pytest.mark.regression
class TestMedicalClearanceGate:
    async def test_adoptable_requires_vet_clearance(self, async_client: AsyncClient, dog_profile_no_clearance):
        resp = await async_client.patch(f"/api/v1/dog/{dog_profile_no_clearance.id}", json={"is_adoptable": True})
        assert resp.status_code in (400, 422), "Dog marked adoptable without vet clearance"


@pytest.mark.regression
class TestFosterToAdopt:
    async def test_foster_conversion_generates_lease(self, async_client: AsyncClient, foster_placement):
        resp = await async_client.post(f"/api/v1/foster/{foster_placement.id}/convert-to-adoption")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data.get("adoption_lease_url") or data.get("adoption_application_id"), "No lease/application generated"


@pytest.mark.regression
class TestRBACBoundarySweep:
    async def test_low_privilege_cannot_access_admin_endpoints(self, async_client, volunteer_token):
        headers = {"Authorization": f"Bearer {volunteer_token}"}
        for endpoint in ["/api/v1/users", "/api/v1/settings", "/api/v1/audit-logs", "/api/v1/finance/transactions"]:
            resp = await async_client.get(endpoint, headers=headers)
            assert resp.status_code == 403, f"RBAC violated: volunteer accessed {endpoint}"
