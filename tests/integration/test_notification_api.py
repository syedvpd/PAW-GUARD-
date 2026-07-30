"""Integration tests for Notification API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Role, User

REGISTER_PAYLOAD = {
    "email": "notifapitest@example.com",
    "password": "StrongP@ss99",
    "full_name": "Notification API Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "notifapitest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestNotificationAPI:
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

    async def test_list_notifications(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/notifications", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    async def test_list_notifications_with_filters(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/notifications?is_read=false", headers=headers)
        assert resp.status_code == 200

    async def test_unread_count(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "count" in data
        assert isinstance(data["count"], int)

    async def test_mark_notification_read_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.put(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=headers)
        assert resp.status_code == 404

    async def test_read_all_notifications(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.put("/api/v1/notifications/read-all", headers=headers)
        assert resp.status_code == 200

    async def test_delete_notification_not_found(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.delete(f"/api/v1/notifications/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_send_notification(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        user_id = (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))).scalar_one().id
        payload = {
            "user_id": str(user_id),
            "title": "Test Notification",
            "body": "This is a test notification body.",
            "notification_type": "general",
        }
        resp = await client.post("/api/v1/notifications/send", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Test Notification"
        assert data["user_id"] == str(user_id)

    async def test_send_notification_with_email(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        user_id = (await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))).scalar_one().id
        payload = {
            "user_id": str(user_id),
            "title": "Email Notification",
            "body": "This notification triggers email.",
            "send_email": True,
        }
        resp = await client.post("/api/v1/notifications/send", json=payload, headers=headers)
        assert resp.status_code == 201

    async def test_get_notification_preferences(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        resp = await client.get("/api/v1/notifications/preferences", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "enable_push" in data
        assert "enable_email" in data
        assert "enable_sms" in data

    async def test_update_notification_preferences(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)
        payload = {"enable_sms": True, "enable_push": False}
        resp = await client.put("/api/v1/notifications/preferences", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enable_sms"] is True
        assert data["enable_push"] is False
