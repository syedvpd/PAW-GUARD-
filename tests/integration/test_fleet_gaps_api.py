"""Fleet PRR 3.13 gaps against a real database: summary SQL, asset register,
one outstanding checkout per asset, and Rescue Agent breakdown reports."""

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, db_session: AsyncSession, role: str = "super_admin") -> dict:
    return await register_and_auth(
        client, db_session, email=f"fleet_{uuid.uuid4().hex[:8]}@example.com", role=role
    )


async def _vehicle(client: AsyncClient, headers: dict, **extra) -> dict:
    resp = await client.post(
        "/api/v1/fleet/vehicles",
        json={
            "make_model": "Ford Transit",
            "license_plate": f"FL-{uuid.uuid4().hex[:6]}",
            **extra,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_create_vehicle_persists_insurance(client: AsyncClient, db_session: AsyncSession):
    headers = await _auth(client, db_session)
    expiry = (date.today() + timedelta(days=10)).isoformat()
    vehicle = await _vehicle(
        client, headers, insurance_provider="SafeGuard", insurance_expiry_date=expiry
    )
    assert vehicle["insurance_provider"] == "SafeGuard"
    assert vehicle["insurance_expiry_date"] == expiry


async def test_summary_uses_latest_maintenance_per_vehicle(
    client: AsyncClient, db_session: AsyncSession
):
    headers = await _auth(client, db_session)
    serviced = await _vehicle(client, headers)
    due = await _vehicle(
        client, headers, insurance_expiry_date=(date.today() + timedelta(days=5)).isoformat()
    )
    today = date.today()

    for vehicle_id, service_date, next_due in (
        (serviced["id"], today - timedelta(days=200), today - timedelta(days=20)),
        (serviced["id"], today - timedelta(days=1), today + timedelta(days=180)),
        (due["id"], today - timedelta(days=100), today + timedelta(days=3)),
    ):
        resp = await client.post(
            "/api/v1/fleet/maintenance",
            json={
                "vehicle_id": vehicle_id,
                "service_date": service_date.isoformat(),
                "next_due_date": next_due.isoformat(),
                "description": "Routine service",
                "maintenance_type": "safety_inspection",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["maintenance_type"] == "safety_inspection"

    resp = await client.get("/api/v1/fleet/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    summary = resp.json()["data"]
    due_ids = {v["id"] for v in summary["maintenance_due"]}
    assert due["id"] in due_ids
    assert serviced["id"] not in due_ids
    assert due["id"] in {v["id"] for v in summary["insurance_expiring"]}
    assert summary["by_status"].get("active", 0) >= 2
    assert summary["total_vehicles"] >= 2


async def test_asset_checkout_is_exclusive(client: AsyncClient, db_session: AsyncSession):
    headers = await _auth(client, db_session)
    serial = f"SN-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/fleet/equipment-assets",
        json={"name": "Net Gun #7", "category": "net_gun", "serial_number": serial},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    asset = resp.json()["data"]

    dup = await client.post(
        "/api/v1/fleet/equipment-assets",
        json={"name": "Other", "serial_number": serial},
        headers=headers,
    )
    assert dup.status_code == 409, dup.text

    first = await client.post(
        "/api/v1/fleet/equipment", json={"asset_id": asset["id"]}, headers=headers
    )
    assert first.status_code == 201, first.text
    checkout = first.json()["data"]
    assert checkout["equipment_name"] == "Net Gun #7"
    assert checkout["asset_id"] == asset["id"]

    second = await client.post(
        "/api/v1/fleet/equipment", json={"asset_id": asset["id"]}, headers=headers
    )
    assert second.status_code == 409, second.text

    listed = await client.get(
        "/api/v1/fleet/equipment-assets", params={"search": serial}, headers=headers
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"][0]["current_checkout_id"] == checkout["id"]

    returned = await client.post(
        f"/api/v1/fleet/equipment/{checkout['id']}/return",
        json={"condition": "needs_repair"},
        headers=headers,
    )
    assert returned.status_code == 200, returned.text
    after = await client.get(f"/api/v1/fleet/equipment-assets/{asset['id']}", headers=headers)
    assert after.json()["data"]["condition"] == "needs_repair"
    assert after.json()["data"]["current_checkout_id"] is None


async def test_rescue_agent_reports_breakdown_but_cannot_checkout(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _auth(client, db_session)
    vehicle = await _vehicle(client, admin)
    agent = await _auth(client, db_session, role="rescue_agent")

    report = await client.post(
        "/api/v1/fleet/breakdowns",
        json={
            "vehicle_id": vehicle["id"],
            "breakdown_type": "Flat tyre",
            "severity": "critical",
            "description": "Stranded on NH-44",
        },
        headers=agent,
    )
    assert report.status_code == 201, report.text

    listed = await client.get(
        "/api/v1/fleet/breakdowns", params={"vehicle_id": vehicle["id"]}, headers=agent
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["data"]) == 1

    checkout = await client.post(
        "/api/v1/fleet/equipment", json={"equipment_name": "Trap"}, headers=agent
    )
    assert checkout.status_code == 403, checkout.text

    summary = await client.get("/api/v1/fleet/summary", headers=admin)
    assert summary.json()["data"]["open_breakdowns"] >= 1
