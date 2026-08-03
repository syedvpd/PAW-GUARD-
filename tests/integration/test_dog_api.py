"""Integration tests for Dog Management API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Role, User
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.shelter.models import ShelterFacility

REGISTER_PAYLOAD = {
    "email": "dogapitest@example.com",
    "password": "StrongP@ss99",
    "full_name": "Dog API Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "dogapitest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestDogAPI:
    async def _auth(self, client: AsyncClient, db_session: AsyncSession) -> dict:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == REGISTER_PAYLOAD["email"])
        )
        user = (await db_session.execute(stmt)).scalar_one()
        role_stmt = select(Role).where(Role.name == "super_admin")
        role = (await db_session.execute(role_stmt)).scalar_one()
        user.roles.append(role)
        user.is_verified = True
        await db_session.commit()
        resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        token = resp.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_register_dog(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {
            "name": "Rex",
            "breed": "Labrador",
            "gender": "male",
            "estimated_age": "3 years",
            "weight": 25.5,
            "color": "black",
            "temperament": "friendly",
            "is_adoptable": True,
            "is_quarantine_passed": True,
        }
        resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Rex"
        assert data["status"] == DogStatus.RESCUED.value
        # is_adoptable is always forced False at registration; it can only be
        # granted via the vet-authorized medical clearance endpoint.
        assert data["is_adoptable"] is False

    async def test_register_dog_validation_error(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.post("/api/v1/dogs", json={"name": ""}, headers=headers)
        assert resp.status_code == 422

    async def test_register_dog_duplicate_microchip_conflict(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """H-2: re-using an existing microchip returns 409, not a 500."""
        headers = await self._auth(client, db_session)
        payload = {
            "name": "Chip Dog",
            "breed": "Labrador",
            "gender": "male",
            "microchip_id": "985141002399999",
        }
        first = await client.post("/api/v1/dogs", json=payload, headers=headers)
        assert first.status_code == 201
        second = await client.post("/api/v1/dogs", json=payload, headers=headers)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONFLICT"

    async def test_get_dog_timeline(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """H-3: a dog's lifecycle activity stream is readable and chronological."""
        headers = await self._auth(client, db_session)
        payload = {"name": "Timeline Dog", "breed": "Beagle", "gender": "male"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        assert create_resp.status_code == 201
        dog_id = create_resp.json()["data"]["id"]

        # A status change appends a second event.
        patch = await client.patch(
            f"/api/v1/dogs/{dog_id}/status",
            json={"status": "shelter"},
            headers=headers,
        )
        assert patch.status_code == 200

        resp = await client.get(f"/api/v1/dogs/{dog_id}/timeline", headers=headers)
        assert resp.status_code == 200
        events = resp.json()["data"]
        event_types = [e["event_type"] for e in events]
        assert "registered" in event_types
        assert "status_changed" in event_types

    async def test_get_dog_timeline_requires_staff(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """H-3: the internal activity stream is not exposed to anonymous users."""
        headers = await self._auth(client, db_session)
        payload = {"name": "Private Dog", "breed": "Pug", "gender": "male"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]

        anon = await client.get(f"/api/v1/dogs/{dog_id}/timeline")
        assert anon.status_code in (401, 403)

    # ── M-1: controlled gender/temperament enums ────────────────────────────

    async def test_register_dog_rejects_unknown_enum_values(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Values outside the controlled sets fail validation (422)."""
        headers = await self._auth(client, db_session)
        resp = await client.post(
            "/api/v1/dogs",
            json={"name": "Bad", "breed": "Lab", "gender": "sparkly"},
            headers=headers,
        )
        assert resp.status_code == 422
        resp = await client.post(
            "/api/v1/dogs",
            json={"name": "Bad", "breed": "Lab", "gender": "male", "temperament": "grumpy"},
            headers=headers,
        )
        assert resp.status_code == 422

    # ── M-3: breed classification (Pure/Mix/Unknown) ────────────────────────

    async def test_register_dog_infers_breed_classification(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Mix-marker breeds default to MIX; the field is explicit-overridable."""
        headers = await self._auth(client, db_session)
        mix = await client.post(
            "/api/v1/dogs",
            json={"name": "Mutt", "breed": "Labrador Mix", "gender": "male"},
            headers=headers,
        )
        assert mix.status_code == 201
        assert mix.json()["data"]["breed_classification"] == "mix"

        pure = await client.post(
            "/api/v1/dogs",
            json={
                "name": "Purebred", "breed": "Labrador", "gender": "male",
                "breed_classification": "pure",
            },
            headers=headers,
        )
        assert pure.status_code == 201
        assert pure.json()["data"]["breed_classification"] == "pure"

    # ── M-2: weight history ─────────────────────────────────────────────────

    async def test_record_weight_and_history(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST /weight appends a log, updates the current weight, and the
        history endpoint returns the chronological trend (PRR 3.4)."""
        headers = await self._auth(client, db_session)
        payload = {"name": "ScaleDog", "breed": "Beagle", "gender": "male", "weight": 15.0}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]

        # Explicit measured_at timestamps keep the history ordering
        # deterministic regardless of when the test runs.
        first = await client.post(
            f"/api/v1/dogs/{dog_id}/weight",
            json={"weight": 16.4, "notes": "Post-surgery", "measured_at": "2026-07-31T09:00:00Z"},
            headers=headers,
        )
        assert first.status_code == 201
        second = await client.post(
            f"/api/v1/dogs/{dog_id}/weight",
            json={"weight": 17.1, "measured_at": "2026-08-01T09:00:00Z"},
            headers=headers,
        )
        assert second.status_code == 201

        # The profile's current weight follows the latest measurement.
        profile = await client.get(f"/api/v1/dogs/{dog_id}", headers=headers)
        assert profile.json()["data"]["weight"] == 17.1

        history = await client.get(f"/api/v1/dogs/{dog_id}/weights", headers=headers)
        assert history.status_code == 200
        entries = history.json()["data"]
        assert len(entries) == 2
        assert [e["weight"] for e in entries] == [16.4, 17.1]
        assert entries[0]["notes"] == "Post-surgery"

    async def test_weight_history_requires_staff(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "ScaleDog2", "breed": "Pug", "gender": "female"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]

        anon = await client.get(f"/api/v1/dogs/{dog_id}/weights")
        assert anon.status_code in (401, 403)

    # ── L-1: visual attributes (PRR 3.4) ───────────────────────────────────

    async def test_visual_attributes_roundtrip(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Ear shape, tail type and distinctive markers survive create + update."""
        headers = await self._auth(client, db_session)
        payload = {
            "name": "MarkerDog", "breed": "Mix", "gender": "male",
            "ear_shape": "floppy", "tail_type": "curled",
            "distinctive_markers": "White patch on chest, notched left ear",
        }
        resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["ear_shape"] == "floppy"
        assert data["tail_type"] == "curled"
        assert data["distinctive_markers"] == "White patch on chest, notched left ear"

        dog_id = data["id"]
        up = await client.put(
            f"/api/v1/dogs/{dog_id}",
            json={"ear_shape": "pricked"},
            headers=headers,
        )
        assert up.status_code == 200
        assert up.json()["data"]["ear_shape"] == "pricked"

    async def test_register_dog_rejects_invalid_visual_enum(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.post(
            "/api/v1/dogs",
            json={"name": "Bad", "breed": "Mix", "gender": "male", "ear_shape": "triangular"},
            headers=headers,
        )
        assert resp.status_code == 422

    # ── L-2/L-3: public directory age / size / location filters (PRR 3.1.4) ──

    async def test_public_directory_age_and_weight_filters(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Anonymous visitors can filter adoptable dogs by age range and
        weight range; age_months is derived from estimated_age."""
        headers = await self._auth(client, db_session)

        young = await client.post(
            "/api/v1/dogs",
            json={"name": "Puppy", "breed": "Mix", "gender": "male", "estimated_age": "6 months", "weight": 4.0},
            headers=headers,
        )
        adult = await client.post(
            "/api/v1/dogs",
            json={"name": "Mature", "breed": "Mix", "gender": "male", "estimated_age": "3 years", "weight": 25.0},
            headers=headers,
        )
        assert young.status_code == adult.status_code == 201
        young_id = young.json()["data"]["id"]
        adult_id = adult.json()["data"]["id"]

        # Make both adoptable so the anonymous directory can see them.
        for dog_id in (young_id, adult_id):
            dog = (
                await db_session.execute(
                    select(DogProfile).where(DogProfile.id == dog_id)
                )
            ).scalar_one()
            dog.is_adoptable = True
        await db_session.commit()

        # Age filter: only the puppy (6 months) is inside [0, 12].
        resp = await client.get("/api/v1/dogs?min_age_months=0&max_age_months=12")
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["data"]]
        assert "Puppy" in names
        assert "Mature" not in names

        # Size (weight) filter: only Mature is >= 20 kg.
        resp = await client.get("/api/v1/dogs?min_weight=20")
        names = [d["name"] for d in resp.json()["data"]]
        assert "Mature" in names
        assert "Puppy" not in names

    async def test_public_directory_location_filter(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Location filter matches the holding shelter facility name/address."""
        headers = await self._auth(client, db_session)

        facility = ShelterFacility(
            name="Happy Tails Shelter",
            address="42 Rescue Lane, Greenfield",
            phone="+1000",
            total_capacity=50,
        )
        db_session.add(facility)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/dogs",
            json={
                "name": "LocDog", "breed": "Mix", "gender": "female",
                "shelter_facility_id": str(facility.id),
            },
            headers=headers,
        )
        assert resp.status_code == 201
        dog_id = resp.json()["data"]["id"]
        dog = (
            await db_session.execute(select(DogProfile).where(DogProfile.id == dog_id))
        ).scalar_one()
        dog.is_adoptable = True
        await db_session.commit()

        # Match on facility name.
        resp = await client.get("/api/v1/dogs?location=Happy%20Tails")
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["data"]]
        assert "LocDog" in names

        # Match on facility address.
        resp = await client.get("/api/v1/dogs?location=Greenfield")
        names = [d["name"] for d in resp.json()["data"]]
        assert "LocDog" in names

        # Non-matching location returns nothing.
        resp = await client.get("/api/v1/dogs?location=Atlantis")
        names = [d["name"] for d in resp.json()["data"]]
        assert "LocDog" not in names

    async def test_list_dogs(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Buddy", "breed": "Beagle", "gender": "male", "estimated_age": "2y", "weight": 15, "color": "brown", "temperament": "friendly"}
        await client.post("/api/v1/dogs", json=payload, headers=headers)
        resp = await client.get("/api/v1/dogs", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "total" in body["meta"]

    async def test_list_dogs_with_filters(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/dogs?status=rescued&is_adoptable=true&breed=Labrador", headers=headers)
        assert resp.status_code == 200

    async def test_get_dog_by_id(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Charlie", "breed": "Pug", "gender": "male", "estimated_age": "1y", "weight": 10, "color": "fawn", "temperament": "friendly"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]
        resp = await client.get(f"/api/v1/dogs/{dog_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Charlie"

    async def test_get_dog_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get(f"/api/v1/dogs/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_update_dog(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Max", "breed": "Husky", "gender": "male", "estimated_age": "4y", "weight": 30, "color": "white", "temperament": "high_energy"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]
        update_payload = {"name": "Maximus", "weight": 32}
        resp = await client.put(f"/api/v1/dogs/{dog_id}", json=update_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Maximus"
        assert resp.json()["data"]["weight"] == 32

    async def test_patch_dog_status(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Luna", "breed": "Indie", "gender": "female", "estimated_age": "2y", "weight": 18, "color": "brown", "temperament": "timid_fearful"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]
        resp = await client.patch(f"/api/v1/dogs/{dog_id}/status", json={"status": "shelter"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == DogStatus.SHELTER.value

    async def test_soft_delete_dog(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"name": "Oscar", "breed": "German Shepherd", "gender": "male", "estimated_age": "3y", "weight": 35, "color": "tan", "temperament": "aggressive"}
        create_resp = await client.post("/api/v1/dogs", json=payload, headers=headers)
        dog_id = create_resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/dogs/{dog_id}", headers=headers)
        assert resp.status_code == 200
        get_resp = await client.get(f"/api/v1/dogs/{dog_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_bulk_status_update(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload1 = {"name": "Bulk1", "breed": "Mix", "gender": "male", "estimated_age": "1y", "weight": 12, "color": "black", "temperament": "friendly"}
        payload2 = {"name": "Bulk2", "breed": "Mix", "gender": "female", "estimated_age": "2y", "weight": 14, "color": "white", "temperament": "friendly"}
        d1 = (await client.post("/api/v1/dogs", json=payload1, headers=headers)).json()["data"]
        d2 = (await client.post("/api/v1/dogs", json=payload2, headers=headers)).json()["data"]
        resp = await client.post("/api/v1/dogs/bulk/status-update", json={"ids": [d1["id"], d2["id"]], "status": "clinic"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["updated_count"] == 2

    async def test_bulk_delete(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload1 = {"name": "Del1", "breed": "Mix", "gender": "male", "estimated_age": "1y", "weight": 11, "color": "brown", "temperament": "friendly"}
        payload2 = {"name": "Del2", "breed": "Mix", "gender": "female", "estimated_age": "2y", "weight": 13, "color": "black", "temperament": "friendly"}
        d1 = (await client.post("/api/v1/dogs", json=payload1, headers=headers)).json()["data"]
        d2 = (await client.post("/api/v1/dogs", json=payload2, headers=headers)).json()["data"]
        resp = await client.post("/api/v1/dogs/bulk/delete", json={"ids": [d1["id"], d2["id"]]}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_count"] == 2
