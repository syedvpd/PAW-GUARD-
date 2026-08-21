"""E2E tests for NOTIFICATIONS module (10 endpoints)."""

import uuid

import pytest
from tests.e2e.helpers import call, uid


@pytest.mark.asyncio
class TestNotificationEndpoints:
    """All 10 notification endpoints."""

    async def test_list_notifications(self, client, setup):
        await call(
            client,
            "notifications",
            "GET",
            "/api/v1/notifications",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_unread_count(self, client, setup):
        await call(
            client,
            "notifications",
            "GET",
            "/api/v1/notifications/unread-count",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_read_all(self, client, setup):
        await call(
            client,
            "notifications",
            "PUT",
            "/api/v1/notifications/read-all",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_send_notification(self, client, setup):
        await call(
            client,
            "notifications",
            "POST",
            "/api/v1/notifications/send",
            headers=setup.admin_headers,
            json={
                "recipient_id": str(setup.admin_user_id)
                if hasattr(setup, "admin_user_id") and setup.admin_user_id
                else str(uuid.uuid4()),
                "title": f"Notification_{uid()}",
                "body": "Test notification",
                "notification_type": "info",
            },
            expected=200,
        )

    async def test_broadcast_notification(self, client, setup):
        await call(
            client,
            "notifications",
            "POST",
            "/api/v1/notifications/broadcast",
            headers=setup.admin_headers,
            json={
                "title": f"Broadcast_{uid()}",
                "body": "Broadcast message",
                "notification_type": "alert",
            },
            expected=200,
        )

    async def test_mark_read(self, client, setup):
        create_r = await client.post(
            "/api/v1/notifications/send",
            json={
                "recipient_id": str(setup.admin_user_id)
                if hasattr(setup, "admin_user_id") and setup.admin_user_id
                else str(uuid.uuid4()),
                "title": f"ReadNotif_{uid()}",
                "body": "Mark as read",
                "notification_type": "info",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code == 200:
            notification_id = create_r.json().get("data", {}).get("id")
            if notification_id:
                await call(
                    client,
                    "notifications",
                    "PUT",
                    f"/api/v1/notifications/{notification_id}/read",
                    headers=setup.admin_headers,
                    expected=200,
                )

    async def test_delete_notification(self, client, setup):
        create_r = await client.post(
            "/api/v1/notifications/send",
            json={
                "recipient_id": str(setup.admin_user_id)
                if hasattr(setup, "admin_user_id") and setup.admin_user_id
                else str(uuid.uuid4()),
                "title": f"DelNotif_{uid()}",
                "body": "To delete",
                "notification_type": "info",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code == 200:
            notification_id = create_r.json().get("data", {}).get("id")
            if notification_id:
                await call(
                    client,
                    "notifications",
                    "DELETE",
                    f"/api/v1/notifications/{notification_id}",
                    headers=setup.admin_headers,
                    expected=200,
                )

    async def test_get_preferences(self, client, setup):
        await call(
            client,
            "notifications",
            "GET",
            "/api/v1/notifications/preferences",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_preferences(self, client, setup):
        await call(
            client,
            "notifications",
            "PUT",
            "/api/v1/notifications/preferences",
            headers=setup.admin_headers,
            json={
                "email_notifications": True,
                "push_notifications": True,
                "sms_notifications": False,
            },
            expected=200,
        )

    async def test_bulk_delete_notifications(self, client, setup):
        create_r = await client.post(
            "/api/v1/notifications/send",
            json={
                "recipient_id": str(setup.admin_user_id)
                if hasattr(setup, "admin_user_id") and setup.admin_user_id
                else str(uuid.uuid4()),
                "title": f"BulkDelNotif_{uid()}",
                "body": "Bulk delete",
                "notification_type": "info",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code == 200:
            notification_id = create_r.json().get("data", {}).get("id")
            if notification_id:
                await call(
                    client,
                    "notifications",
                    "POST",
                    "/api/v1/notifications/bulk/delete",
                    headers=setup.admin_headers,
                    json={
                        "ids": [notification_id],
                    },
                    expected=200,
                )
