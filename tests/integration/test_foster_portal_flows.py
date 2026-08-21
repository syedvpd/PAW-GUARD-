"""Integration tests for PawGuard Foster Portal workflows & API gaps."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.foster.models import (
    FosterPlacement,
    FosterProfile,
    FosterStatus,
)
from pawguard.modules.medical.models import MedicalClearance


@pytest.mark.asyncio
class TestFosterPortalFlows:
    async def test_foster_self_profile_and_placements(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Test GET /fosters/me and GET /fosters/me/placements endpoints."""
        email = f"foster_parent_{uuid.uuid4().hex[:6]}@example.com"
        headers = await register_and_auth(client, db_session, email=email)

        # 1. Initially no profile -> 404
        resp = await client.get("/api/v1/fosters/me", headers=headers)
        assert resp.status_code == 404

        # 2. Apply for foster profile
        apply_payload = {
            "preferences": "Puppies, Senior dogs",
            "max_capacity": 2,
            "notes": "Fenced yard with previous dog care experience",
        }
        apply_resp = await client.post("/api/v1/fosters/apply", json=apply_payload, headers=headers)
        assert apply_resp.status_code == 201
        profile_data = apply_resp.json()["data"]
        foster_id = profile_data["id"]

        # 3. GET /fosters/me returns the profile
        me_resp = await client.get("/api/v1/fosters/me", headers=headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["data"]["id"] == foster_id
        assert me_resp.json()["data"]["max_capacity"] == 2

        # 4. Approve the foster profile & assign a dog placement
        user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
        foster_prof = (
            await db_session.execute(
                select(FosterProfile).where(FosterProfile.user_id == user.id)
            )
        ).scalar_one()
        foster_prof.status = FosterStatus.APPROVED
        foster_prof.is_available = True

        dog = DogProfile(
            registration_number=f"DOG-{uuid.uuid4().hex[:6]}",
            name="Buddy",
            breed="Golden Retriever",
            status=DogStatus.SHELTER,
            is_adoptable=True,
        )
        db_session.add(dog)
        await db_session.commit()

        placement = FosterPlacement(
            foster_id=foster_prof.id,
            dog_id=dog.id,
            placed_at=datetime.now(UTC),
            is_active=True,
            notes="Active foster placement for recovery",
        )
        db_session.add(placement)
        dog.status = DogStatus.FOSTERED
        foster_prof.active_count = 1
        await db_session.commit()

        # 5. GET /fosters/me/placements returns placement
        placements_resp = await client.get("/api/v1/fosters/me/placements", headers=headers)
        assert placements_resp.status_code == 200
        p_list = placements_resp.json()["data"]
        assert len(p_list) == 1
        assert p_list[0]["id"] == str(placement.id)
        assert p_list[0]["dog"]["name"] == "Buddy"

    async def test_foster_supply_request_flow(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Test POST /fosters/placements/{id}/supplies/request endpoint."""
        email = f"foster_supplies_{uuid.uuid4().hex[:6]}@example.com"
        headers = await register_and_auth(client, db_session, email=email)

        # Apply & setup placement
        await client.post(
            "/api/v1/fosters/apply",
            json={"preferences": "Medical Recovery", "max_capacity": 1},
            headers=headers,
        )
        user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
        foster_prof = (
            await db_session.execute(
                select(FosterProfile).where(FosterProfile.user_id == user.id)
            )
        ).scalar_one()
        foster_prof.status = FosterStatus.APPROVED

        dog = DogProfile(
            registration_number=f"DOG-{uuid.uuid4().hex[:6]}",
            name="Max",
            breed="Beagle",
            status=DogStatus.FOSTERED,
            is_adoptable=True,
        )
        db_session.add(dog)
        await db_session.commit()

        placement = FosterPlacement(
            foster_id=foster_prof.id,
            dog_id=dog.id,
            placed_at=datetime.now(UTC),
            is_active=True,
        )
        db_session.add(placement)
        await db_session.commit()

        # Request supplies
        supply_payload = {
            "item_type": "food",
            "description": "20lb Bag of Puppy Kibble",
            "quantity": 2,
        }
        resp = await client.post(
            f"/api/v1/fosters/placements/{placement.id}/supplies/request",
            json=supply_payload,
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["item_type"] == "food"
        assert data["quantity"] == 2
        assert "[REQUESTED]" in data["description"]

        # View supplies list for placement
        view_resp = await client.get(
            f"/api/v1/fosters/placements/{placement.id}/supplies",
            headers=headers,
        )
        assert view_resp.status_code == 200
        assert len(view_resp.json()["data"]) == 1

    async def test_foster_to_adopt_conversion(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Test POST /fosters/placements/{id}/convert-to-adopt by placement owner."""
        email = f"foster_adopt_{uuid.uuid4().hex[:6]}@example.com"
        headers = await register_and_auth(client, db_session, email=email)

        # Setup placement
        await client.post(
            "/api/v1/fosters/apply",
            json={"preferences": "Any", "max_capacity": 1},
            headers=headers,
        )
        user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
        foster_prof = (
            await db_session.execute(
                select(FosterProfile).where(FosterProfile.user_id == user.id)
            )
        ).scalar_one()
        foster_prof.status = FosterStatus.APPROVED

        dog = DogProfile(
            registration_number=f"DOG-{uuid.uuid4().hex[:6]}",
            name="Luna",
            breed="Husky",
            status=DogStatus.FOSTERED,
            is_adoptable=True,
        )
        db_session.add(dog)
        await db_session.commit()

        # Medical clearance requirement
        clearance = MedicalClearance(
            dog_id=dog.id,
            authorized_by_id=user.id,
            clearance_type="adoption_surgery",
            status="approved",
            authorized_at=datetime.now(UTC),
            decision_notes="Passed all health checks.",
        )
        db_session.add(clearance)

        placement = FosterPlacement(
            foster_id=foster_prof.id,
            dog_id=dog.id,
            placed_at=datetime.now(UTC),
            is_active=True,
        )
        db_session.add(placement)
        await db_session.commit()

        # Perform Foster-to-Adopt conversion
        resp = await client.post(
            f"/api/v1/fosters/placements/{placement.id}/convert-to-adopt",
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "adoption_id" in data

    async def test_cross_foster_authorization_isolation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Verify strict authorization isolation between Foster A and Foster B."""
        email_a = f"foster_a_{uuid.uuid4().hex[:6]}@example.com"
        email_b = f"foster_b_{uuid.uuid4().hex[:6]}@example.com"

        headers_a = await register_and_auth(client, db_session, email=email_a, role="general_public")
        headers_b = await register_and_auth(client, db_session, email=email_b, role="general_public")

        # Setup Foster A and Placement A
        await client.post("/api/v1/fosters/apply", json={"max_capacity": 1}, headers=headers_a)
        user_a = (await db_session.execute(select(User).where(User.email == email_a))).scalar_one()
        prof_a = (await db_session.execute(select(FosterProfile).where(FosterProfile.user_id == user_a.id))).scalar_one()
        prof_a.status = FosterStatus.APPROVED

        dog_a = DogProfile(registration_number=f"DOG-{uuid.uuid4().hex[:6]}", name="Dog A", breed="Lab", status=DogStatus.FOSTERED, is_adoptable=True)
        db_session.add(dog_a)
        await db_session.commit()

        placement_a = FosterPlacement(foster_id=prof_a.id, dog_id=dog_a.id, placed_at=datetime.now(UTC), is_active=True)
        db_session.add(placement_a)

        # Setup Foster B and Placement B
        await client.post("/api/v1/fosters/apply", json={"max_capacity": 1}, headers=headers_b)
        user_b = (await db_session.execute(select(User).where(User.email == email_b))).scalar_one()
        prof_b = (await db_session.execute(select(FosterProfile).where(FosterProfile.user_id == user_b.id))).scalar_one()
        prof_b.status = FosterStatus.APPROVED

        dog_b = DogProfile(registration_number=f"DOG-{uuid.uuid4().hex[:6]}", name="Dog B", breed="Poodle", status=DogStatus.FOSTERED, is_adoptable=True)
        db_session.add(dog_b)
        await db_session.commit()

        placement_b = FosterPlacement(foster_id=prof_b.id, dog_id=dog_b.id, placed_at=datetime.now(UTC), is_active=True)
        db_session.add(placement_b)
        await db_session.commit()

        # 1. GET /fosters/me returns only logged-in foster's profile
        me_a = await client.get("/api/v1/fosters/me", headers=headers_a)
        assert me_a.json()["data"]["id"] == str(prof_a.id)

        me_b = await client.get("/api/v1/fosters/me", headers=headers_b)
        assert me_b.json()["data"]["id"] == str(prof_b.id)

        # 2. GET /fosters/me/placements returns only logged-in foster's placement
        p_a = await client.get("/api/v1/fosters/me/placements", headers=headers_a)
        assert len(p_a.json()["data"]) == 1
        assert p_a.json()["data"][0]["id"] == str(placement_a.id)

        p_b = await client.get("/api/v1/fosters/me/placements", headers=headers_b)
        assert len(p_b.json()["data"]) == 1
        assert p_b.json()["data"][0]["id"] == str(placement_b.id)

        # 3. Foster A cannot submit progress for Foster B's placement -> 403
        progress_payload = {"weight_kg": 15.0, "feeding_notes": "Eating well"}
        resp_prog = await client.post(
            f"/api/v1/fosters/placements/{placement_b.id}/progress",
            json=progress_payload,
            headers=headers_a,
        )
        assert resp_prog.status_code == 403

        # 4. Foster A cannot request supplies for Foster B's placement -> 403
        supply_payload = {"item_type": "food", "quantity": 1, "description": "Kibble"}
        resp_sup = await client.post(
            f"/api/v1/fosters/placements/{placement_b.id}/supplies/request",
            json=supply_payload,
            headers=headers_a,
        )
        assert resp_sup.status_code == 403

        # 5. Foster A cannot convert Foster B's placement to adoption -> 403
        resp_conv = await client.post(
            f"/api/v1/fosters/placements/{placement_b.id}/convert-to-adopt",
            headers=headers_a,
        )
        assert resp_conv.status_code == 403

    async def test_inactive_placement_operations_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Verify inactive placements cannot perform active operations."""
        email = f"foster_inactive_{uuid.uuid4().hex[:6]}@example.com"
        headers = await register_and_auth(client, db_session, email=email)

        await client.post("/api/v1/fosters/apply", json={"max_capacity": 1}, headers=headers)
        user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
        prof = (await db_session.execute(select(FosterProfile).where(FosterProfile.user_id == user.id))).scalar_one()
        prof.status = FosterStatus.APPROVED

        dog = DogProfile(registration_number=f"DOG-{uuid.uuid4().hex[:6]}", name="Old Dog", breed="Boxer", status=DogStatus.SHELTER, is_adoptable=True)
        db_session.add(dog)
        await db_session.commit()

        # Inactive placement
        placement = FosterPlacement(foster_id=prof.id, dog_id=dog.id, placed_at=datetime.now(UTC), is_active=False)
        db_session.add(placement)
        await db_session.commit()

        # Request supplies on inactive placement -> 409 Conflict
        resp_sup = await client.post(
            f"/api/v1/fosters/placements/{placement.id}/supplies/request",
            json={"item_type": "food", "quantity": 1},
            headers=headers,
        )
        assert resp_sup.status_code == 409

    async def test_staff_permissions_and_admin_supply_dispatch(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Verify Staff permissions and existing Admin supply dispatch functionality."""
        email_foster = f"foster_target_{uuid.uuid4().hex[:6]}@example.com"
        email_staff = f"staff_coordinator_{uuid.uuid4().hex[:6]}@example.com"

        foster_headers = await register_and_auth(client, db_session, email=email_foster)
        staff_headers = await register_and_auth(client, db_session, email=email_staff)

        # Setup foster profile & placement
        await client.post("/api/v1/fosters/apply", json={"max_capacity": 1}, headers=foster_headers)
        user_foster = (await db_session.execute(select(User).where(User.email == email_foster))).scalar_one()
        prof = (await db_session.execute(select(FosterProfile).where(FosterProfile.user_id == user_foster.id))).scalar_one()
        prof.status = FosterStatus.APPROVED

        dog = DogProfile(registration_number=f"DOG-{uuid.uuid4().hex[:6]}", name="Staff Dog", breed="Husky", status=DogStatus.FOSTERED, is_adoptable=True)
        db_session.add(dog)
        await db_session.commit()

        placement = FosterPlacement(foster_id=prof.id, dog_id=dog.id, placed_at=datetime.now(UTC), is_active=True)
        db_session.add(placement)
        await db_session.commit()

        # Admin supply dispatch POST /placements/{id}/supplies with staff headers -> 201 Created
        dispatch_payload = {"item_type": "crate", "quantity": 1, "description": "Large Dog Crate"}
        dispatch_resp = await client.post(
            f"/api/v1/fosters/placements/{placement.id}/supplies",
            json=dispatch_payload,
            headers=staff_headers,
        )
        assert dispatch_resp.status_code == 201
        assert dispatch_resp.json()["data"]["item_type"] == "crate"

    async def test_vetting_and_home_inspection_update(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Verify updating vetting and home inspection fields on a foster profile."""
        email_foster = f"foster_vetting_{uuid.uuid4().hex[:6]}@example.com"
        email_staff = f"staff_vetter_{uuid.uuid4().hex[:6]}@example.com"

        foster_headers = await register_and_auth(client, db_session, email=email_foster, role="general_public")
        staff_headers = await register_and_auth(client, db_session, email=email_staff, role="super_admin")

        # Foster applies
        apply_resp = await client.post("/api/v1/fosters/apply", json={"max_capacity": 2}, headers=foster_headers)
        assert apply_resp.status_code == 201
        foster_id = apply_resp.json()["data"]["id"]

        # Staff updates vetting & home inspection fields
        update_payload = {
            "status": "approved",
            "background_check_passed": True,
            "references_checked": True,
            "vetting_notes": "All 3 references verified, clear criminal record.",
            "home_inspection_passed": True,
            "home_inspection_notes": "6ft fenced backyard, no hazards.",
            "home_inspection_address": "100 Rescue Avenue, Paw City",
        }
        update_resp = await client.put(f"/api/v1/fosters/{foster_id}", json=update_payload, headers=staff_headers)
        assert update_resp.status_code == 200
        data = update_resp.json()["data"]
        assert data["background_check_passed"] is True
        assert data["references_checked"] is True
        assert data["vetting_notes"] == "All 3 references verified, clear criminal record."
        assert data["home_inspection_passed"] is True
        assert data["home_inspection_notes"] == "6ft fenced backyard, no hazards."
        assert data["home_inspection_address"] == "100 Rescue Avenue, Paw City"
        assert data["vetted_at"] is not None
        assert data["inspected_at"] is not None
