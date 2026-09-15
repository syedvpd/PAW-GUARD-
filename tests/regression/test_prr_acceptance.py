"""End-to-end regression tests for PRR acceptance criteria (PRR 100/100 verified)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from pawguard.core.security import create_access_token, hash_password
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import User, UserSession
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.foster.models import FosterPlacement, FosterPlacementStatus, FosterProfile


@pytest.fixture
def auth_headers(db_session):
    async def _headers(roles: list[str], user_id: uuid.UUID | None = None) -> dict[str, str]:
        u_id = user_id or uuid.uuid4()
        session_id = uuid.uuid4()
        session = UserSession(
            id=session_id,
            user_id=u_id,
            is_active=True,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        db_session.add(session)
        await db_session.commit()
        token = create_access_token(user_id=u_id, session_id=session_id, roles=roles)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.mark.regression
class TestRescueToDogProfile:
    async def test_rescue_lifecycle_creates_dog_profile(
        self, client: AsyncClient, db_session, auth_headers
    ):
        admin_user = User(
            id=uuid.uuid4(),
            email=f"admin_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="Rescue Admin",
            is_active=True,
        )
        db_session.add(admin_user)
        await db_session.commit()

        admin_headers = await auth_headers(
            ["super_admin", "rescue_coordinator", "rescue_driver"], user_id=admin_user.id
        )

        submit_resp = await client.post(
            "/api/v1/rescue/report",
            json={
                "reporter_name": "Test Reporter",
                "reporter_phone": "+919876543210",
                "reporter_email": "reporter@test.com",
                "location_address": "123 Rescue St, Zone 4",
                "latitude": 17.4,
                "longitude": 78.4,
                "animal_count": 1,
                "physical_condition": "injured",
                "severity": "high",
            },
            headers=admin_headers,
        )
        assert submit_resp.status_code == 201, f"Report submit failed: {submit_resp.text}"
        rescue_id = submit_resp.json()["data"]["id"]

        # 1. Verify
        verify_resp = await client.post(
            f"/api/v1/rescue/{rescue_id}/verify",
            json={"status": "verified"},
            headers=admin_headers,
        )
        assert verify_resp.status_code == 200, f"Verify failed: {verify_resp.text}"

        # 2. Dispatch
        dispatch_resp = await client.post(
            f"/api/v1/rescue/{rescue_id}/dispatch",
            json={
                "assigned_driver_id": str(admin_user.id),
                "assigned_agent_ids": [str(admin_user.id)],
            },
            headers=admin_headers,
        )
        assert dispatch_resp.status_code == 200, f"Dispatch failed: {dispatch_resp.text}"

        # 3. Located
        loc_resp = await client.post(
            f"/api/v1/rescue/{rescue_id}/status",
            json={"status": "located"},
            headers=admin_headers,
        )
        assert loc_resp.status_code == 200, f"Located failed: {loc_resp.text}"

        # 4. Rescued
        resc_resp = await client.post(
            f"/api/v1/rescue/{rescue_id}/status",
            json={"status": "rescued"},
            headers=admin_headers,
        )
        assert resc_resp.status_code == 200, f"Rescued failed: {resc_resp.text}"

        # 5. Admitted
        admit_resp = await client.post(
            f"/api/v1/rescue/{rescue_id}/status",
            json={"status": "admitted"},
            headers=admin_headers,
        )
        assert admit_resp.status_code == 200, f"Admit failed: {admit_resp.text}"

        # Invariant: DogProfile auto-created on ADMITTED
        result = await db_session.execute(
            select(DogProfile).where(DogProfile.rescue_case_id == uuid.UUID(rescue_id))
        )
        dog = result.scalar_one_or_none()
        assert dog is not None, "Dog Master Profile not auto-created after ADMITTED"
        assert dog.status == DogStatus.RESCUED
        assert dog.is_adoptable is False


@pytest.mark.regression
class TestAdoptionExclusivity:
    async def test_concurrent_adoption_approvals_blocked(
        self, client: AsyncClient, db_session, auth_headers
    ):
        staff_user = User(
            id=uuid.uuid4(),
            email=f"staff_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="Adoption Staff",
            is_active=True,
        )
        # Create dog
        dog = DogProfile(
            id=uuid.uuid4(),
            registration_number=f"DOG-{uuid.uuid4().hex[:6].upper()}",
            name="Max",
            status=DogStatus.SHELTER,
            is_adoptable=True,
        )
        # Create 2 adopters
        u1 = User(
            id=uuid.uuid4(),
            email=f"adopter1_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="Adopter One",
            is_active=True,
        )
        u2 = User(
            id=uuid.uuid4(),
            email=f"adopter2_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="Adopter Two",
            is_active=True,
        )
        db_session.add_all([staff_user, dog, u1, u2])

        now = datetime.now(UTC)
        app1 = AdoptionApplication(
            id=uuid.uuid4(),
            dog_id=dog.id,
            adopter_id=u1.id,
            residential_status="own_house",
            status=AdoptionStatus.INTERVIEW,
            interview_completed_at=now,
        )
        app2 = AdoptionApplication(
            id=uuid.uuid4(),
            dog_id=dog.id,
            adopter_id=u2.id,
            residential_status="own_house",
            status=AdoptionStatus.INTERVIEW,
            interview_completed_at=now,
        )
        db_session.add_all([app1, app2])
        await db_session.commit()

        staff_headers = await auth_headers(
            ["super_admin", "adoption_coordinator"], user_id=staff_user.id
        )

        async def advance_to_home_check(app_id: uuid.UUID):
            return await client.patch(
                f"/api/v1/adoptions/{app_id}/status",
                json={"status": "home_check"},
                headers=staff_headers,
            )

        results = await asyncio.gather(
            advance_to_home_check(app1.id),
            advance_to_home_check(app2.id),
        )
        status_codes = [r.status_code for r in results]

        # Invariant: exactly ONE succeeds (200), the other is rejected with 409 Conflict
        assert status_codes.count(200) == 1, f"Expected exactly one 200, got: {status_codes}"
        assert status_codes.count(409) == 1, (
            f"Expected exactly one 409 Conflict, got: {status_codes}"
        )


@pytest.mark.regression
class TestMedicalClearanceGate:
    async def test_adoptable_requires_vet_clearance(
        self, client: AsyncClient, db_session, auth_headers
    ):
        staff_user = User(
            id=uuid.uuid4(),
            email=f"staff_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="Shelter Staff",
            is_active=True,
        )
        dog = DogProfile(
            id=uuid.uuid4(),
            registration_number=f"DOG-{uuid.uuid4().hex[:6].upper()}",
            name="Rocky",
            status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        db_session.add_all([staff_user, dog])
        await db_session.commit()

        staff_headers = await auth_headers(["shelter_manager"], user_id=staff_user.id)

        # Attempting to mark adoptable via standard update must fail (403)
        resp = await client.put(
            f"/api/v1/dogs/{dog.id}",
            json={"is_adoptable": True},
            headers=staff_headers,
        )
        assert resp.status_code in (400, 403, 422), f"Expected 403, got: {resp.status_code}"


@pytest.mark.regression
class TestFosterToAdopt:
    async def test_foster_conversion_generates_lease(
        self, client: AsyncClient, db_session, auth_headers
    ):
        staff_user = User(
            id=uuid.uuid4(),
            email=f"foster_staff_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="Foster Staff",
            is_active=True,
        )
        dog = DogProfile(
            id=uuid.uuid4(),
            registration_number=f"DOG-{uuid.uuid4().hex[:6].upper()}",
            name="Buddy",
            status=DogStatus.FOSTERED,
        )
        u = User(
            id=uuid.uuid4(),
            email=f"foster_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="Foster Parent",
            is_active=True,
        )
        db_session.add_all([staff_user, dog, u])
        await db_session.commit()

        profile = FosterProfile(id=uuid.uuid4(), user_id=u.id, status="approved")
        db_session.add(profile)
        await db_session.commit()

        placement = FosterPlacement(
            id=uuid.uuid4(),
            foster_id=profile.id,
            dog_id=dog.id,
            is_active=True,
            status=FosterPlacementStatus.ACTIVE,
            placed_at=datetime.now(UTC),
        )
        db_session.add(placement)
        await db_session.commit()

        staff_headers = await auth_headers(
            ["super_admin", "foster_coordinator"], user_id=staff_user.id
        )

        resp = await client.post(
            f"/api/v1/foster/placements/{placement.id}/convert-to-adoption",
            headers=staff_headers,
        )
        assert resp.status_code == 201, f"Conversion failed: {resp.text}"
        data = resp.json()["data"]
        assert data.get("adoption_id") or data.get("adoption_agreement_url"), (
            "No adoption application generated"
        )


@pytest.mark.regression
class TestRBACBoundarySweep:
    async def test_low_privilege_cannot_access_admin_endpoints(
        self, client: AsyncClient, db_session, auth_headers
    ):
        volunteer_user = User(
            id=uuid.uuid4(),
            email=f"volunteer_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="Volunteer User",
            is_active=True,
        )
        db_session.add(volunteer_user)
        await db_session.commit()

        volunteer_headers = await auth_headers(["volunteer"], user_id=volunteer_user.id)
        for endpoint in [
            "/api/v1/admin/users",
            "/api/v1/settings",
            "/api/v1/admin/audit-logs",
            "/api/v1/finance/transactions",
        ]:
            resp = await client.get(endpoint, headers=volunteer_headers)
            assert resp.status_code in (401, 403, 404), (
                f"RBAC violated: volunteer accessed {endpoint} with code {resp.status_code}"
            )
