import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth


async def _admin(client: AsyncClient, db_session: AsyncSession) -> dict:
    return await register_and_auth(
        client, db_session, email=f"kennel_{uuid.uuid4().hex[:8]}@example.com"
    )


async def _kennel(client: AsyncClient, headers: dict) -> tuple[str, str]:
    facility = await client.post(
        "/api/v1/shelter/facilities",
        json={"name": f"Dog house {uuid.uuid4().hex[:6]}", "address": "1 Lane", "phone": "+1234567890"},
        headers=headers,
    )
    assert facility.status_code == 201, facility.text
    section = await client.post(
        f"/api/v1/shelter/facilities/{facility.json()['data']['id']}/sections",
        json={"name": "Section - B"},
        headers=headers,
    )
    assert section.status_code == 201, section.text
    kennel = await client.post(
        f"/api/v1/shelter/sections/{section.json()['data']['id']}/kennels",
        json={"identifier": "K-101"},
        headers=headers,
    )
    assert kennel.status_code == 201, kennel.text
    assert kennel.json()["data"]["sanitation_state"] == "clean"
    return kennel.json()["data"]["section_id"], kennel.json()["data"]["id"]


async def _set(client: AsyncClient, headers: dict, kennel_id: str, status: str):
    return await client.put(
        f"/api/v1/shelter/kennels/{kennel_id}/sanitation",
        params={"status_val": status},
        headers=headers,
    )


async def _persisted_state(client: AsyncClient, headers: dict, section_id: str, kennel_id: str) -> str:
    resp = await client.get(f"/api/v1/shelter/sections/{section_id}/kennels", headers=headers)
    assert resp.status_code == 200, resp.text
    return next(k for k in resp.json()["data"] if k["id"] == kennel_id)["sanitation_state"]


@pytest.mark.asyncio
class TestKennelSanitationApi:
    async def test_full_sanitation_cycle_persists(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin(client, db_session)
        section_id, kennel_id = await _kennel(client, headers)

        for status in ("needs_cleaning", "disinfecting", "clean", "out_of_service", "clean"):
            resp = await _set(client, headers, kennel_id, status)
            assert resp.status_code == 200, resp.text
            assert resp.json()["data"]["sanitation_state"] == status
            assert await _persisted_state(client, headers, section_id, kennel_id) == status

    async def test_cleaning_log_from_needs_cleaning_returns_to_clean(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin(client, db_session)
        section_id, kennel_id = await _kennel(client, headers)
        assert (await _set(client, headers, kennel_id, "needs_cleaning")).status_code == 200

        resp = await client.post(
            f"/api/v1/shelter/kennels/{kennel_id}/cleaning-logs",
            json={"method": "disinfectant", "notes": "rotation"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert await _persisted_state(client, headers, section_id, kennel_id) == "clean"

    async def test_unknown_status_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin(client, db_session)
        section_id, kennel_id = await _kennel(client, headers)
        resp = await _set(client, headers, kennel_id, "filthy")
        assert resp.status_code == 422
        assert await _persisted_state(client, headers, section_id, kennel_id) == "clean"

    async def test_unauthorized_role_cannot_update(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin(client, db_session)
        section_id, kennel_id = await _kennel(client, headers)
        donor = await register_and_auth(
            client, db_session, email=f"donor_{uuid.uuid4().hex[:8]}@example.com", role="donor"
        )
        resp = await _set(client, donor, kennel_id, "needs_cleaning")
        assert resp.status_code == 403
        assert await _persisted_state(client, headers, section_id, kennel_id) == "clean"

    async def test_unauthenticated_cannot_update(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin(client, db_session)
        section_id, kennel_id = await _kennel(client, headers)
        resp = await _set(client, {}, kennel_id, "needs_cleaning")
        assert resp.status_code == 401
        assert await _persisted_state(client, headers, section_id, kennel_id) == "clean"
