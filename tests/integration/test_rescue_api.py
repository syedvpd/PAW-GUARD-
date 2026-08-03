"""Integration tests for Emergency Rescue API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

from pawguard.modules.auth.models import User
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
        return await register_and_auth(
            client, db_session, email=REGISTER_PAYLOAD["email"]
        )

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

    async def test_dispatch_rescue_with_escalation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Escalation Protocol request is stored on the dispatch (M-D)."""
        headers = await self._auth(client, db_session)
        user_id = (
            await db_session.execute(
                select(User).where(User.email == REGISTER_PAYLOAD["email"])
            )
        ).scalar_one().id
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Esc", "reporter_phone": "+112",
                  "location_address": "Esc Rd", "physical_condition": "Critical"},
            headers=headers,
        )
        cid = r.json()["data"]["id"]
        await client.post(f"/api/v1/rescue/{cid}/verify", json={"status": "verified"}, headers=headers)
        resp = await client.post(
            f"/api/v1/rescue/{cid}/dispatch",
            json={
                "assigned_driver_id": str(user_id),
                "vehicle_id": "VAN-008",
                "escalation_type": "vet_transport",
                "escalation_notes": "Specialized veterinary transport required",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        dispatch = resp.json()["data"]["dispatch"]
        assert dispatch["escalation_type"] == "vet_transport"
        assert dispatch["escalation_notes"] == "Specialized veterinary transport required"

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
        user_id = (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))).scalar_one().id
        report_payload = {"reporter_name": "Fail", "reporter_phone": "+777", "location_address": "Fail Rd", "physical_condition": "Stray"}
        r = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        cid = r.json()["data"]["id"]
        await client.post(f"/api/v1/rescue/{cid}/verify", json={"status": "verified"}, headers=headers)
        await client.post(f"/api/v1/rescue/{cid}/dispatch", json={"assigned_driver_id": str(user_id), "vehicle_id": "VAN-006"}, headers=headers)
        resp = await client.post(f"/api/v1/rescue/{cid}/fail?failure_reason=Animal%20fled", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == RescueStatus.VERIFIED.value
        # Canonical PRR 3.3 outcome code stored, not free text (M-1).
        assert resp.json()["data"]["dispatch"]["failure_reason"] == "animal_fled"

    async def test_fail_rescue_normalises_legacy_reason(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Legacy free-text reasons are stored as canonical outcome codes (M-1)."""
        headers = await self._auth(client, db_session)
        user_id = (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))).scalar_one().id
        report_payload = {"reporter_name": "Fail2", "reporter_phone": "+778", "location_address": "Fail2 Rd", "physical_condition": "Injured"}
        r = await client.post("/api/v1/rescue/report", json=report_payload, headers=headers)
        cid = r.json()["data"]["id"]
        await client.post(f"/api/v1/rescue/{cid}/verify", json={"status": "verified"}, headers=headers)
        await client.post(f"/api/v1/rescue/{cid}/dispatch", json={"assigned_driver_id": str(user_id), "vehicle_id": "VAN-007"}, headers=headers)
        resp = await client.post(f"/api/v1/rescue/{cid}/fail?failure_reason=Area%20Inaccessible", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["dispatch"]["failure_reason"] == "area_inaccessible"

    async def test_list_rescue_requests(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/rescue", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "total" in body["meta"]

    async def test_list_rescue_with_filters(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/rescue?status=reported", headers=headers)
        assert resp.status_code == 200

    async def test_public_status_lookup(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """A reporter can look up their own case status without auth by
        providing the ticket number AND the phone they reported with (M-E)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Status", "reporter_phone": "+113",
                  "location_address": "Status Rd", "physical_condition": "Injured"},
            headers=headers,
        )
        ticket = r.json()["data"]["ticket_number"]
        resp = await client.get(
            f"/api/v1/rescue/status?ticket_number={ticket}&phone=%2B113"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ticket_number"] == ticket
        assert data["status"] == RescueStatus.REPORTED.value
        # Public response carries no reporter PII.
        assert "reporter_name" not in data
        assert "reporter_phone" not in data

    async def test_public_status_lookup_wrong_phone_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A mismatched phone must not resolve the case (M-E)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Status2", "reporter_phone": "+114",
                  "location_address": "Status2 Rd", "physical_condition": "Injured"},
            headers=headers,
        )
        ticket = r.json()["data"]["ticket_number"]
        resp = await client.get(
            f"/api/v1/rescue/status?ticket_number={ticket}&phone=%2B9999999999"
        )
        assert resp.status_code == 404

    async def test_public_status_lookup_unknown_ticket_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """An unknown ticket yields 404, identical to the wrong-phone case so
        ticket numbers cannot be enumerated (M-E)."""
        resp = await client.get(
            "/api/v1/rescue/status?ticket_number=RES-00000000-0000&phone=%2B9999999999"
        )
        assert resp.status_code == 404

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

    async def test_bulk_status_update_legal_transition(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Bulk REPORTED -> VERIFIED applies when every request is eligible."""
        headers = await self._auth(client, db_session)
        ids = []
        for i in range(2):
            r = await client.post(
                "/api/v1/rescue/report",
                json={"reporter_name": f"Bulk{i}", "reporter_phone": f"+10{i}", "location_address": f"Bulk Rd {i}", "physical_condition": "Injured"},
                headers=headers,
            )
            assert r.status_code == 201
            ids.append(r.json()["data"]["id"])

        resp = await client.post(
            "/api/v1/rescue/bulk/status-update",
            json={"ids": ids, "status": "verified"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["updated_count"] == 2

    async def test_bulk_status_update_blocks_illegal_jump(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Bulk REPORTED -> ADMITTED must be rejected with 409 (H-1)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Jump", "reporter_phone": "+101", "location_address": "Jump Rd", "physical_condition": "Injured"},
            headers=headers,
        )
        cid = r.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/rescue/bulk/status-update",
            json={"ids": [cid], "status": "admitted"},
            headers=headers,
        )
        assert resp.status_code == 409
        # Request must be untouched.
        check = await client.get(f"/api/v1/rescue/{cid}", headers=headers)
        assert check.json()["data"]["status"] == RescueStatus.REPORTED.value

    async def test_bulk_status_update_blocks_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Bulk REJECTED is ambiguous - must be a 422 (H-1)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Rej", "reporter_phone": "+102", "location_address": "Rej Rd", "physical_condition": "Injured"},
            headers=headers,
        )
        cid = r.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/rescue/bulk/status-update",
            json={"ids": [cid], "status": "rejected"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_report_incident_normalises_legacy_condition(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Legacy free-text condition labels map to canonical enum values (H-2)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Norm", "reporter_phone": "+103", "location_address": "Norm Rd", "physical_condition": "Injured/Fractured"},
            headers=headers,
        )
        assert r.status_code == 201
        assert r.json()["data"]["physical_condition"] == "fractured_injured"

    async def test_report_incident_with_media_evidence(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Intake media object keys are stored and echoed back (M-B)."""
        headers = await self._auth(client, db_session)
        media = ["rescue/2026/08/photo_1.jpg", "rescue/2026/08/clip_2.mp4"]
        r = await client.post(
            "/api/v1/rescue/report",
            json={
                "reporter_name": "Media", "reporter_phone": "+109",
                "location_address": "Media Rd", "physical_condition": "Injured",
                "media_evidence": media,
            },
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["media_evidence"] == media

    async def test_report_incident_rejects_too_many_media(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """More than 5 media items fail validation (M-B)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={
                "reporter_name": "Media2", "reporter_phone": "+110",
                "location_address": "Media2 Rd", "physical_condition": "Injured",
                "media_evidence": [f"rescue/2026/08/p{i}.jpg" for i in range(6)],
            },
            headers=headers,
        )
        assert r.status_code == 422

    async def test_report_incident_with_environmental_factors_and_notes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Environmental factors + reporter notes are stored and echoed (M-C)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={
                "reporter_name": "Env", "reporter_phone": "+111",
                "location_address": "Env Rd", "physical_condition": "Injured",
                "environmental_factors": "Heavy rain, flooding",
                "reporter_notes": "Dog is very timid",
            },
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["environmental_factors"] == "Heavy rain, flooding"
        assert data["reporter_notes"] == "Dog is very timid"

    async def test_report_incident_rejects_unknown_condition(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Values outside the controlled set fail validation (H-2)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Bad", "reporter_phone": "+104", "location_address": "Bad Rd", "physical_condition": "Sparkly Unicorn"},
            headers=headers,
        )
        assert r.status_code == 422

    async def test_report_incident_with_severity_and_urgent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Intake severity / urgent flag are stored and echoed back (M-A)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={
                "reporter_name": "Sev", "reporter_phone": "+105",
                "location_address": "Sev Rd", "physical_condition": "Injured",
                "severity": "high", "is_urgent": True,
            },
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["severity"] == "high"
        assert data["is_urgent"] is True

    async def test_report_incident_defaults_severity_medium(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Unset severity defaults to medium on intake (M-A)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Sev2", "reporter_phone": "+106",
                  "location_address": "Sev2 Rd", "physical_condition": "Stray"},
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["severity"] == "medium"
        assert data["is_urgent"] is False

    async def test_verify_refines_severity(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Coordinators refine severity / urgent flag during verification (M-A)."""
        headers = await self._auth(client, db_session)
        r = await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Sev3", "reporter_phone": "+107",
                  "location_address": "Sev3 Rd", "physical_condition": "Injured"},
            headers=headers,
        )
        cid = r.json()["data"]["id"]
        resp = await client.post(
            f"/api/v1/rescue/{cid}/verify",
            json={"status": "verified", "severity": "critical", "is_urgent": True},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == RescueStatus.VERIFIED.value
        assert data["severity"] == "critical"
        assert data["is_urgent"] is True

    async def test_list_rescue_filter_by_severity_and_urgent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """List endpoint filters by severity and the urgent flag (M-A)."""
        headers = await self._auth(client, db_session)
        await client.post(
            "/api/v1/rescue/report",
            json={"reporter_name": "Sev4", "reporter_phone": "+108",
                  "location_address": "Sev4 Rd", "physical_condition": "Injured",
                  "severity": "critical", "is_urgent": True},
            headers=headers,
        )
        resp = await client.get(
            "/api/v1/rescue?severity=critical&urgent_only=true", headers=headers
        )
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert items
        assert all(i["severity"] == "critical" for i in items)
        assert all(i["is_urgent"] is True for i in items)
