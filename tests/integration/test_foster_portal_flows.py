"""Integration tests for PawGuard Foster Portal workflows & API gaps."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

from pawguard.modules.auth.models import Role, User
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.foster.models import (
    FosterPlacement,
    FosterProfile,
    FosterStatus,
    SupplyItemType,
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
