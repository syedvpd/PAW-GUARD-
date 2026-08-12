"""E2E tests for GRIEVANCE module (16 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestGrievanceEndpoints:
    """All 16 grievance endpoints."""

    async def test_create_grievance(self, client, setup):
        r = await call(client, "grievance", "POST", "/api/v1/grievance",
                       json={
                           "reporter_name": f"Reporter_{uid()}",
                           "reporter_phone": "+9876543210",
                           "complaint_type": "service_quality",
                           "details": "Test grievance details",
                       }, expected=201)
        TEST.grievance_ticket_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_grievances(self, client, setup):
        r = await call(client, "grievance", "GET", "/api/v1/grievance",
                       headers=setup.admin_headers, expected=200)

    async def test_get_grievance(self, client, setup):
        if TEST.grievance_ticket_id:
            ticket_id = str(TEST.grievance_ticket_id)
        else:
            create_r = await client.post("/api/v1/grievance", json={
                "reporter_name": f"Reporter_{uid()}",
                "reporter_phone": "+9876543210",
                "complaint_type": "animal_welfare",
                "details": "Get grievance",
            })
            ticket_id = create_r.json()["data"]["id"]
        r = await call(client, "grievance", "GET",
                       f"/api/v1/grievance/{ticket_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_get_grievance_not_found(self, client, setup):
        fake_id = str(uuid.uuid4())
        r = await call(client, "grievance", "GET", f"/api/v1/grievance/{fake_id}",
                       headers=setup.admin_headers, expected=404)

    async def test_update_grievance(self, client, setup):
        if TEST.grievance_ticket_id:
            ticket_id = str(TEST.grievance_ticket_id)
        else:
            create_r = await client.post("/api/v1/grievance", json={
                "reporter_name": f"Reporter_{uid()}",
                "reporter_phone": "+9876543210",
                "complaint_type": "service_quality",
                "details": "Update grievance",
            })
            ticket_id = create_r.json()["data"]["id"]
        r = await call(client, "grievance", "PUT",
                       f"/api/v1/grievance/{ticket_id}",
                       headers=setup.admin_headers, json={
                           "details": "Updated grievance details",
                       }, expected=200)

    async def test_delete_grievance(self, client, setup):
        create_r = await client.post("/api/v1/grievance", json={
            "reporter_name": f"DelReporter_{uid()}",
            "reporter_phone": "+9876543210",
            "complaint_type": "service_quality",
            "details": "To delete",
        })
        if create_r.status_code in (200, 201):
            ticket_id = create_r.json()["data"]["id"]
            r = await call(client, "grievance", "DELETE",
                           f"/api/v1/grievance/{ticket_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_update_grievance_status(self, client, setup):
        if TEST.grievance_ticket_id:
            ticket_id = str(TEST.grievance_ticket_id)
        else:
            create_r = await client.post("/api/v1/grievance", json={
                "reporter_name": f"Reporter_{uid()}",
                "reporter_phone": "+9876543210",
                "complaint_type": "service_quality",
                "details": "Status grievance",
            })
            ticket_id = create_r.json()["data"]["id"]
        r = await call(client, "grievance", "PATCH",
                       f"/api/v1/grievance/{ticket_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "in_progress",
                       }, expected=200)

    async def test_assign_grievance(self, client, setup):
        if TEST.grievance_ticket_id:
            ticket_id = str(TEST.grievance_ticket_id)
        else:
            create_r = await client.post("/api/v1/grievance", json={
                "reporter_name": f"Reporter_{uid()}",
                "reporter_phone": "+9876543210",
                "complaint_type": "service_quality",
                "details": "Assign grievance",
            })
            ticket_id = create_r.json()["data"]["id"]
        r = await call(client, "grievance", "POST",
                       f"/api/v1/grievance/{ticket_id}/assign",
                       headers=setup.admin_headers, json={
                           "assigned_to": str(setup.admin_user_id) if hasattr(setup, 'admin_user_id') and setup.admin_user_id else str(uuid.uuid4()),
                       }, expected=200)

    async def test_escalate_grievance(self, client, setup):
        if TEST.grievance_ticket_id:
            ticket_id = str(TEST.grievance_ticket_id)
        else:
            create_r = await client.post("/api/v1/grievance", json={
                "reporter_name": f"Reporter_{uid()}",
                "reporter_phone": "+9876543210",
                "complaint_type": "animal_welfare",
                "details": "Escalate grievance",
            })
            ticket_id = create_r.json()["data"]["id"]
        r = await call(client, "grievance", "POST",
                       f"/api/v1/grievance/{ticket_id}/escalate",
                       headers=setup.admin_headers, expected=200)

    async def test_list_grievance_comments(self, client, setup):
        if TEST.grievance_ticket_id:
            ticket_id = str(TEST.grievance_ticket_id)
        else:
            create_r = await client.post("/api/v1/grievance", json={
                "reporter_name": f"Reporter_{uid()}",
                "reporter_phone": "+9876543210",
                "complaint_type": "service_quality",
                "details": "Comments grievance",
            })
            ticket_id = create_r.json()["data"]["id"]
        r = await call(client, "grievance", "GET",
                       f"/api/v1/grievance/{ticket_id}/comments",
                       headers=setup.admin_headers, expected=200)

    async def test_add_grievance_comment(self, client, setup):
        if TEST.grievance_ticket_id:
            ticket_id = str(TEST.grievance_ticket_id)
        else:
            create_r = await client.post("/api/v1/grievance", json={
                "reporter_name": f"Reporter_{uid()}",
                "reporter_phone": "+9876543210",
                "complaint_type": "service_quality",
                "details": "Add comment grievance",
            })
            ticket_id = create_r.json()["data"]["id"]
        r = await call(client, "grievance", "POST",
                       f"/api/v1/grievance/{ticket_id}/comments",
                       headers=setup.admin_headers, json={
                           "comment": "Investigating the issue",
                       }, expected=200)

    # ── Feedback ─────────────────────────────────────────────────────────

    async def test_create_feedback(self, client, setup):
        r = await call(client, "grievance", "POST", "/api/v1/grievance/feedback",
                       json={
                           "rating": 5,
                           "comments": "Great service!",
                       }, expected=201)
        TEST.feedback_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_feedback(self, client, setup):
        r = await call(client, "grievance", "GET", "/api/v1/grievance/feedback",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_feedback(self, client, setup):
        create_r = await client.post("/api/v1/grievance/feedback", json={
            "rating": 3,
            "comments": "To delete",
        })
        if create_r.status_code in (200, 201):
            feedback_id = create_r.json()["data"]["id"]
            r = await call(client, "grievance", "DELETE",
                           f"/api/v1/grievance/feedback/{feedback_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_grievances(self, client, setup):
        create_r = await client.post("/api/v1/grievance", json={
            "reporter_name": f"BulkDel_{uid()}",
            "reporter_phone": "+9876543210",
            "complaint_type": "service_quality",
            "details": "Bulk delete",
        })
        if create_r.status_code in (200, 201):
            ticket_id = create_r.json()["data"]["id"]
            r = await call(client, "grievance", "POST",
                           "/api/v1/grievance/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [ticket_id],
                           }, expected=200)

    async def test_bulk_status_grievances(self, client, setup):
        if TEST.grievance_ticket_id:
            ticket_id = str(TEST.grievance_ticket_id)
        else:
            create_r = await client.post("/api/v1/grievance", json={
                "reporter_name": f"BulkStat_{uid()}",
                "reporter_phone": "+9876543210",
                "complaint_type": "service_quality",
                "details": "Bulk status",
            })
            ticket_id = create_r.json()["data"]["id"]
        r = await call(client, "grievance", "POST",
                       "/api/v1/grievance/bulk/status",
                       headers=setup.admin_headers, json={
                           "ids": [ticket_id],
                           "status": "resolved",
                       }, expected=200)

    async def test_bulk_delete_feedback(self, client, setup):
        create_r = await client.post("/api/v1/grievance/feedback", json={
            "rating": 4,
            "comments": "Bulk del feedback",
        })
        if create_r.status_code in (200, 201):
            feedback_id = create_r.json()["data"]["id"]
            r = await call(client, "grievance", "POST",
                           "/api/v1/grievance/feedback/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [feedback_id],
                           }, expected=200)
