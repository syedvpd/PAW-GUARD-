"""E2E tests for RESCUE module (30 endpoints).

20 rescue + 2 public rescue + 8 rescue centres = 30 endpoints.
"""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestRescueEndpoints:
    """All 20 rescue endpoints."""

    async def test_create_rescue_report(self, client, setup):
        r = await call(client, "rescue", "POST", "/api/v1/rescue/report",
                       headers=setup.admin_headers, json={
                           "reporter_name": f"Reporter_{uid()}",
                           "reporter_phone": "+9876543210",
                           "location_address": "456 Emergency Road",
                           "animal_count": 1,
                           "physical_condition": "injured",
                           "severity": "high",
                           "is_urgent": False,
                       }, expected=201)
        TEST.rescue_request_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_rescue_requests(self, client, setup):
        r = await call(client, "rescue", "GET", "/api/v1/rescue",
                       headers=setup.admin_headers, expected=200)

    async def test_get_rescue_status(self, client, setup):
        r = await call(client, "rescue", "GET", "/api/v1/rescue/status",
                       headers=setup.admin_headers, expected=200)

    async def test_get_rescue_request(self, client, setup):
        if TEST.rescue_request_id:
            req_id = str(TEST.rescue_request_id)
        else:
            create_r = await client.post("/api/v1/rescue/report", json={
                "reporter_name": f"Reporter_{uid()}",
                "reporter_phone": "+9876543210",
                "location_address": "789 Rescue St",
                "animal_count": 1,
                "physical_condition": "stable",
                "severity": "medium",
                "is_urgent": False,
            }, headers=setup.admin_headers)
            req_id = create_r.json()["data"]["id"]
        r = await call(client, "rescue", "GET", f"/api/v1/rescue/{req_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_rescue_request(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"DelReporter_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "Del Rescue St",
            "animal_count": 1,
            "physical_condition": "injured",
            "severity": "low",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue", "DELETE", f"/api/v1/rescue/{req_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_dispatch_rescue(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"DispatchReporter_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "Dispatch Road",
            "animal_count": 1,
            "physical_condition": "critical",
            "severity": "high",
            "is_urgent": True,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue", "POST",
                           f"/api/v1/rescue/{req_id}/dispatch",
                           headers=setup.admin_headers, json={
                               "notes": "Deploying rescue team",
                           }, expected=200)

    async def test_verify_rescue(self, client, setup):
        if TEST.rescue_request_id:
            req_id = str(TEST.rescue_request_id)
        else:
            create_r = await client.post("/api/v1/rescue/report", json={
                "reporter_name": f"VerifyReporter_{uid()}",
                "reporter_phone": "+9876543210",
                "location_address": "Verify Road",
                "animal_count": 1,
                "physical_condition": "stable",
                "severity": "medium",
                "is_urgent": False,
            }, headers=setup.admin_headers)
            req_id = create_r.json()["data"]["id"]
        r = await call(client, "rescue", "POST",
                       f"/api/v1/rescue/{req_id}/verify",
                       headers=setup.admin_headers, expected=200)

    async def test_located_rescue(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"LocReporter_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "Located Road",
            "animal_count": 1,
            "physical_condition": "stable",
            "severity": "medium",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue", "POST",
                           f"/api/v1/rescue/{req_id}/located",
                           headers=setup.admin_headers, expected=200)

    async def test_secured_rescue(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"SecReporter_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "Secured Road",
            "animal_count": 1,
            "physical_condition": "injured",
            "severity": "high",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue", "POST",
                           f"/api/v1/rescue/{req_id}/secured",
                           headers=setup.admin_headers, expected=200)

    async def test_admitted_rescue(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"AdmReporter_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "Admitted Road",
            "animal_count": 1,
            "physical_condition": "stable",
            "severity": "medium",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue", "POST",
                           f"/api/v1/rescue/{req_id}/admitted",
                           headers=setup.admin_headers, expected=200)

    async def test_fail_rescue(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"FailReporter_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "Fail Road",
            "animal_count": 1,
            "physical_condition": "deceased",
            "severity": "critical",
            "is_urgent": True,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue", "POST",
                           f"/api/v1/rescue/{req_id}/fail",
                           headers=setup.admin_headers, json={
                               "reason": "Animal not found",
                           }, expected=200)

    async def test_escalate_rescue(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"EscReporter_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "Escalate Road",
            "animal_count": 3,
            "physical_condition": "critical",
            "severity": "critical",
            "is_urgent": True,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue", "POST",
                           f"/api/v1/rescue/{req_id}/escalate",
                           headers=setup.admin_headers, expected=200)

    async def test_media_upload_url(self, client, setup):
        r = await call(client, "rescue", "POST", "/api/v1/rescue/media-upload-url",
                       headers=setup.admin_headers, json={
                           "filename": f"rescue_{uid()}.jpg",
                           "mime_type": "image/jpeg",
                       }, expected=200)

    async def test_bulk_delete_rescue(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"BulkDel_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "BulkDel Road",
            "animal_count": 1,
            "physical_condition": "stable",
            "severity": "low",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue", "POST", "/api/v1/rescue/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [req_id],
                           }, expected=200)

    async def test_bulk_status_update_rescue(self, client, setup):
        if TEST.rescue_request_id:
            req_id = str(TEST.rescue_request_id)
        else:
            create_r = await client.post("/api/v1/rescue/report", json={
                "reporter_name": f"BulkStat_{uid()}",
                "reporter_phone": "+9876543210",
                "location_address": "BulkStat Road",
                "animal_count": 1,
                "physical_condition": "stable",
                "severity": "medium",
                "is_urgent": False,
            }, headers=setup.admin_headers)
            req_id = create_r.json()["data"]["id"]
        r = await call(client, "rescue", "POST", "/api/v1/rescue/bulk/status-update",
                       headers=setup.admin_headers, json={
                           "ids": [req_id],
                           "status": "verified",
                       }, expected=200)

    async def test_list_dispatches(self, client, setup):
        r = await call(client, "rescue", "GET", "/api/v1/rescue/dispatches",
                       headers=setup.admin_headers, expected=200)

    async def test_update_dispatch(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"DispUpd_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "DispatchUpd Road",
            "animal_count": 1,
            "physical_condition": "stable",
            "severity": "medium",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            disp_r = await client.post(f"/api/v1/rescue/{req_id}/dispatch",
                                       json={"notes": "Team dispatched"},
                                       headers=setup.admin_headers)
            if disp_r.status_code == 200:
                dispatch_id = disp_r.json().get("data", {}).get("id")
                if dispatch_id:
                    r = await call(client, "rescue", "PATCH",
                                   f"/api/v1/rescue/dispatches/{dispatch_id}",
                                   headers=setup.admin_headers, json={
                                       "notes": "Updated notes",
                                   }, expected=200)

    async def test_delete_dispatch(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"DispDel_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "DispatchDel Road",
            "animal_count": 1,
            "physical_condition": "stable",
            "severity": "low",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            disp_r = await client.post(f"/api/v1/rescue/{req_id}/dispatch",
                                       json={"notes": "To delete"},
                                       headers=setup.admin_headers)
            if disp_r.status_code == 200:
                dispatch_id = disp_r.json().get("data", {}).get("id")
                if dispatch_id:
                    r = await call(client, "rescue", "DELETE",
                                   f"/api/v1/rescue/dispatches/{dispatch_id}",
                                   headers=setup.admin_headers, expected=200)

    async def test_update_dispatch_alt(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"DispAlt_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "DispatchAlt Road",
            "animal_count": 1,
            "physical_condition": "stable",
            "severity": "medium",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            disp_r = await client.post(f"/api/v1/rescue/{req_id}/dispatch",
                                       json={"notes": "Alt dispatch"},
                                       headers=setup.admin_headers)
            if disp_r.status_code == 200:
                dispatch_id = disp_r.json().get("data", {}).get("id")
                if dispatch_id:
                    r = await call(client, "rescue", "PATCH",
                                   f"/api/v1/rescue/dispatch/{dispatch_id}",
                                   headers=setup.admin_headers, json={
                                       "notes": "Alt updated",
                                   }, expected=200)

    async def test_delete_dispatch_alt(self, client, setup):
        create_r = await client.post("/api/v1/rescue/report", json={
            "reporter_name": f"DispDelAlt_{uid()}",
            "reporter_phone": "+9876543210",
            "location_address": "DispatchDelAlt Road",
            "animal_count": 1,
            "physical_condition": "stable",
            "severity": "low",
            "is_urgent": False,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            req_id = create_r.json()["data"]["id"]
            disp_r = await client.post(f"/api/v1/rescue/{req_id}/dispatch",
                                       json={"notes": "To delete alt"},
                                       headers=setup.admin_headers)
            if disp_r.status_code == 200:
                dispatch_id = disp_r.json().get("data", {}).get("id")
                if dispatch_id:
                    r = await call(client, "rescue", "DELETE",
                                   f"/api/v1/rescue/dispatch/{dispatch_id}",
                                   headers=setup.admin_headers, expected=200)


@pytest.mark.asyncio
class TestPublicRescueEndpoints:
    """2 public rescue endpoints."""

    async def test_public_report_rescue(self, client):
        r = await call(client, "public_rescue", "POST",
                       "/api/v1/public/rescue/report",
                       json={
                           "reporter_name": f"PubReporter_{uid()}",
                           "reporter_phone": "+9876543210",
                           "location_address": "Public Rescue Road",
                           "animal_count": 1,
                           "physical_condition": "injured",
                           "severity": "high",
                           "is_urgent": False,
                       }, expected=200)

    async def test_public_report_rescue_invalid(self, client):
        r = await call(client, "public_rescue", "POST",
                       "/api/v1/public/rescue/report",
                       json={}, expected=422)


@pytest.mark.asyncio
class TestRescueCentreEndpoints:
    """8 rescue centre endpoints."""

    async def test_list_rescue_centres(self, client, setup):
        r = await call(client, "rescue_centres", "GET",
                       "/api/v1/rescue-centres",
                       headers=setup.admin_headers, expected=200)

    async def test_create_rescue_centre(self, client, setup):
        r = await call(client, "rescue_centres", "POST",
                       "/api/v1/rescue-centres",
                       headers=setup.admin_headers, json={
                           "name": f"Centre_{uid()}",
                           "address": "123 Centre Road",
                           "phone": "+1122334455",
                           "latitude": 28.6139,
                           "longitude": 77.2090,
                           "total_capacity": 100,
                       }, expected=201)
        TEST.facility_id = uuid.UUID(r.json()["data"]["id"])

    async def test_get_rescue_centre(self, client, setup):
        if TEST.facility_id:
            fac_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/rescue-centres", json={
                "name": f"Centre_{uid()}",
                "address": "456 Centre Road",
                "phone": "+1122334455",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 50,
            }, headers=setup.admin_headers)
            fac_id = create_r.json()["data"]["id"]
        r = await call(client, "rescue_centres", "GET",
                       f"/api/v1/rescue-centres/{fac_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_update_rescue_centre(self, client, setup):
        if TEST.facility_id:
            fac_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/rescue-centres", json={
                "name": f"Centre_{uid()}",
                "address": "789 Centre Road",
                "phone": "+1122334455",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 50,
            }, headers=setup.admin_headers)
            fac_id = create_r.json()["data"]["id"]
        r = await call(client, "rescue_centres", "PUT",
                       f"/api/v1/rescue-centres/{fac_id}",
                       headers=setup.admin_headers, json={
                           "name": "Updated Centre",
                           "total_capacity": 75,
                       }, expected=200)

    async def test_delete_rescue_centre(self, client, setup):
        create_r = await client.post("/api/v1/rescue-centres", json={
            "name": f"DelCentre_{uid()}",
            "address": "Del Centre Road",
            "phone": "+1122334455",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "total_capacity": 30,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            fac_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue_centres", "DELETE",
                           f"/api/v1/rescue-centres/{fac_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_update_rescue_centre_status(self, client, setup):
        if TEST.facility_id:
            fac_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/rescue-centres", json={
                "name": f"StatCentre_{uid()}",
                "address": "Stat Centre Road",
                "phone": "+1122334455",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 50,
            }, headers=setup.admin_headers)
            fac_id = create_r.json()["data"]["id"]
        r = await call(client, "rescue_centres", "PUT",
                       f"/api/v1/rescue-centres/{fac_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "active",
                       }, expected=200)

    async def test_bulk_delete_rescue_centres(self, client, setup):
        create_r = await client.post("/api/v1/rescue-centres", json={
            "name": f"BulkDelCentre_{uid()}",
            "address": "BulkDel Road",
            "phone": "+1122334455",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "total_capacity": 20,
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            fac_id = create_r.json()["data"]["id"]
            r = await call(client, "rescue_centres", "POST",
                           "/api/v1/rescue-centres/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [fac_id],
                           }, expected=200)

    async def test_bulk_status_rescue_centres(self, client, setup):
        if TEST.facility_id:
            fac_id = str(TEST.facility_id)
        else:
            create_r = await client.post("/api/v1/rescue-centres", json={
                "name": f"BulkStatCentre_{uid()}",
                "address": "BulkStat Road",
                "phone": "+1122334455",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "total_capacity": 50,
            }, headers=setup.admin_headers)
            fac_id = create_r.json()["data"]["id"]
        r = await call(client, "rescue_centres", "POST",
                       "/api/v1/rescue-centres/bulk/status",
                       headers=setup.admin_headers, json={
                           "ids": [fac_id],
                           "status": "active",
                       }, expected=200)
