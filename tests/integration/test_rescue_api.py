"""Integration tests for Emergency Rescue API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Role, User
from pawguard.modules.rescue.models import RescueStatus

REGISTER_PAYLOAD = {
    "email": "rescueapitest@example.com",
    "password": "StrongP@ss99",
    "full_name": "Rescue API Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "rescueapitest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestRescueAPI:
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

    async def test_report_incident(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {
            "reporter_name": "Jane Public",
            "reporter_phone": "+9876543210",
            "location_address": "Street 5, Block B",
            "physical_condition": "Injured",
            "animal_count": 2,
            "latitude": 17.4482,
            "longitude": 78.3741,
        }
        resp = await client.post("/api/v1/rescue/report", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["status"] == RescueStatus.REPORTED.value
        assert "RES-" in data["ticket_number"]

    async def test_report_incident_validation_error(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.post("/api/v1/rescue/report", json={}, headers=headers)
        assert resp.status_code == 422

    async def test_verify_rescue(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        report_payload = {"reporter_name": "John", "reporter_phone": "+111", "location_address": "Test Rd", "physical_condition": "Sick"}
        report_resp = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        case_id = report_resp.json()["data"]["id"]
        resp = await client.post(f"/api/v1/rescue/{case_id}/verify", json={"status": "verified"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == RescueStatus.VERIFIED.value

    async def test_verify_rescue_reject(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        report_payload = {"reporter_name": "John", "reporter_phone": "+222", "location_address": "Reject Rd", "physical_condition": "Stray"}
        report_resp = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        case_id = report_resp.json()["data"]["id"]
        resp = await client.post(f"/api/v1/rescue/{case_id}/verify", json={"status": "rejected", "rejection_rationale": "False alarm"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == RescueStatus.REJECTED.value

    async def test_dispatch_rescue(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        user_id = (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))).scalar_one().id
        report_payload = {"reporter_name": "Dispatch", "reporter_phone": "+333", "location_address": "Dispatch Rd", "physical_condition": "Critical"}
        report_resp = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        case_id = report_resp.json()["data"]["id"]
        await client.post(f"/api/v1/rescue/{case_id}/verify", json={"status": "verified"}, headers=headers)
        dispatch_payload = {"assigned_driver_id": str(user_id), "vehicle_id": "VAN-002", "equipment_details": "Cage, Net"}
        resp = await client.post(f"/api/v1/rescue/{case_id}/dispatch", json=dispatch_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == RescueStatus.DISPATCHED.value

    async def test_located_rescue(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        user_id = (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))).scalar_one().id
        report_payload = {"reporter_name": "Located", "reporter_phone": "+444", "location_address": "Located Rd", "physical_condition": "Injured"}
        r = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        cid = r.json()["data"]["id"]
        await client.post(f"/api/v1/rescue/{cid}/verify", json={"status": "verified"}, headers=headers)
        await client.post(f"/api/v1/rescue/{cid}/dispatch", json={"assigned_driver_id": str(user_id), "vehicle_id": "VAN-003"}, headers=headers)
        resp = await client.post(f"/api/v1/rescue/{cid}/located", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == RescueStatus.LOCATED.value

    async def test_secured_rescue(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        user_id = (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))).scalar_one().id
        report_payload = {"reporter_name": "Secured", "reporter_phone": "+555", "location_address": "Secured Rd", "physical_condition": "Injured"}
        r = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        cid = r.json()["data"]["id"]
        await client.post(f"/api/v1/rescue/{cid}/verify", json={"status": "verified"}, headers=headers)
        await client.post(f"/api/v1/rescue/{cid}/dispatch", json={"assigned_driver_id": str(user_id), "vehicle_id": "VAN-004"}, headers=headers)
        await client.post(f"/api/v1/rescue/{cid}/located", headers=headers)
        resp = await client.post(f"/api/v1/rescue/{cid}/secured", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == RescueStatus.RESCUED.value

    async def test_admitted_rescue(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        user_id = (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))).scalar_one().id
        report_payload = {"reporter_name": "Admit", "reporter_phone": "+666", "location_address": "Admit Rd", "physical_condition": "Critical"}
        r = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        cid = r.json()["data"]["id"]
        await client.post(f"/api/v1/rescue/{cid}/verify", json={"status": "verified"}, headers=headers)
        await client.post(f"/api/v1/rescue/{cid}/dispatch", json={"assigned_driver_id": str(user_id), "vehicle_id": "VAN-005"}, headers=headers)
        await client.post(f"/api/v1/rescue/{cid}/located", headers=headers)
        await client.post(f"/api/v1/rescue/{cid}/secured", headers=headers)
        admit_payload = {"notes": "Admitted with minor injuries", "photos": ["http://example.com/photo.jpg"]}
        resp = await client.post(f"/api/v1/rescue/{cid}/admitted", json=admit_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == RescueStatus.ADMITTED.value

    async def test_fail_rescue(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        report_payload = {"reporter_name": "Fail", "reporter_phone": "+777", "location_address": "Fail Rd", "physical_condition": "Stray"}
        r = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        cid = r.json()["data"]["id"]
        await client.post(f"/api/v1/rescue/{cid}/verify", json={"status": "verified"}, headers=headers)
        resp = await client.post(f"/api/v1/rescue/{cid}/fail?failure_reason=Animal%20not%20found", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == RescueStatus.REJECTED.value

    async def test_list_rescue_requests(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/rescue", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    async def test_list_rescue_with_filters(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/rescue?status=reported", headers=headers)
        assert resp.status_code == 200

    async def test_get_rescue_by_id(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        report_payload = {"reporter_name": "Get", "reporter_phone": "+888", "location_address": "Get Rd", "physical_condition": "Sick"}
        r = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        cid = r.json()["data"]["id"]
        resp = await client.get(f"/api/v1/rescue/{cid}", headers=headers)
        assert resp.status_code == 200

    async def test_get_rescue_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get(f"/api/v1/rescue/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_soft_delete_rescue(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        report_payload = {"reporter_name": "Delete", "reporter_phone": "+999", "location_address": "Delete Rd", "physical_condition": "Injured"}
        r = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        cid = r.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/rescue/{cid}", headers=headers)
        assert resp.status_code == 200
        get_resp = await client.get(f"/api/v1/rescue/{cid}", headers=headers)
        assert get_resp.status_code == 404
