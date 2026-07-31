"""Integration tests for newly wired modules: inventory, shelter, medical, portal, fleet, grievance, notifications, dashboard, settings, storage."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Permission, Role, User

REGISTER_PAYLOAD = {
    "email": "newmodtest@example.com",
    "password": "StrongP@ss99",
    "full_name": "New Module Tester",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "newmodtest@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestNewModules:
    async def _auth(self, client: AsyncClient, db_session: AsyncSession) -> dict:
        """Register, promote to super_admin, login, return auth headers."""
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == REGISTER_PAYLOAD["email"])
        )
        user = (await db_session.execute(stmt)).scalar_one()
        role_stmt = select(Role).options(selectinload(Role.permissions)).where(Role.name == "super_admin")
        role = (await db_session.execute(role_stmt)).scalar_one()
        required_codes = [
            "reports:read", "reports:create", "reports:export_pdf", "reports:export_csv", "reports:export_excel",
            "finance:create", "finance:read", "finance:update",
        ]
        for code in required_codes:
            perm_stmt = select(Permission).where(Permission.code == code)
            perm = (await db_session.execute(perm_stmt)).scalar_one_or_none()
            if perm is None:
                perm = Permission(code=code, description=code)
                db_session.add(perm)
                await db_session.flush()
            if perm not in role.permissions:
                role.permissions.append(perm)
        user.roles.append(role)
        user.is_verified = True
        await db_session.commit()

        resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        token = resp.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_inventory_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        item_payload = {"name": "Test Med Kit", "category": "pharmaceutical", "quantity": 100, "unit": "units", "reorder_threshold": 10}
        resp = await client.post("/api/v1/inventory/items", json=item_payload, headers=headers)
        assert resp.status_code == 201
        item_id = resp.json()["data"]["id"]

        resp = await client.get("/api/v1/inventory/items", headers=headers)
        assert resp.status_code == 200

        mov_payload = {"item_id": str(item_id), "movement_type": "check_in", "quantity": 50, "notes": "restock"}
        resp = await client.post("/api/v1/inventory/movements", json=mov_payload, headers=headers)
        assert resp.status_code == 201

        req_payload = {"item_id": str(item_id), "quantity": 5}
        resp = await client.post("/api/v1/inventory/requisitions", json=req_payload, headers=headers)
        assert resp.status_code == 201
        req_id = resp.json()["data"]["id"]

        resp = await client.put(
            f"/api/v1/inventory/requisitions/{req_id}/status",
            json={"status": "approved"},
            headers=headers,
        )
        assert resp.status_code == 200

    async def test_shelter_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        fac_payload = {"name": "Test Shelter", "address": "123 Test St", "phone": "+1234", "total_capacity": 50}
        resp = await client.post("/api/v1/shelter/facilities", json=fac_payload, headers=headers)
        assert resp.status_code == 201
        fac_id = resp.json()["data"]["id"]

        sec_payload = {"name": "Quarantine", "capacity": 10}
        resp = await client.post(f"/api/v1/shelter/facilities/{fac_id}/sections", json=sec_payload, headers=headers)
        assert resp.status_code == 201
        sec_id = resp.json()["data"]["id"]

        ken_payload = {"identifier": "K-01", "capacity": 2}
        resp = await client.post(f"/api/v1/shelter/sections/{sec_id}/kennels", json=ken_payload, headers=headers)
        assert resp.status_code == 201

    async def test_medical_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        dog_payload = {"name": "MedDog", "breed": "Lab", "gender": "male", "estimated_age": "3y", "weight": 20, "color": "black", "temperament": "calm"}
        resp = await client.post("/api/v1/dogs", json=dog_payload, headers=headers)
        assert resp.status_code == 201
        dog_id = resp.json()["data"]["id"]

        exam_payload = {"dog_id": str(dog_id), "exam_date": "2026-07-29T10:00:00Z", "body_condition_score": 5, "triage_diagnosis": "Healthy"}
        resp = await client.post("/api/v1/medical/exams", json=exam_payload, headers=headers)
        assert resp.status_code == 201

        vac_payload = {"dog_id": str(dog_id), "vaccine_name": "Rabies", "administered_at": "2026-07-29T10:00:00Z"}
        resp = await client.post("/api/v1/medical/vaccinations", json=vac_payload, headers=headers)
        assert resp.status_code == 201

        rx_payload = {"dog_id": str(dog_id), "drug_name": "Amoxicillin", "dosage": "500mg", "route": "oral", "start_at": "2026-07-29T10:00:00Z", "end_at": "2026-08-05T10:00:00Z"}
        resp = await client.post("/api/v1/medical/prescriptions", json=rx_payload, headers=headers)
        assert resp.status_code == 201

        resp = await client.get(f"/api/v1/medical/dogs/{dog_id}/history", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["exams"]) >= 1
        assert len(data["vaccinations"]) >= 1

    async def test_portal_cms_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        story_payload = {"title": "Saved Barnaby", "summary": "A happy tail", "body": "Full story here", "status": "published"}
        resp = await client.post("/api/v1/portal/admin/success-stories", json=story_payload, headers=headers)
        assert resp.status_code == 201

        blog_payload = {"title": "Awareness Post", "slug": "awareness-1", "excerpt": "Excerpt", "body": "Full body", "status": "published", "category": "awareness"}
        resp = await client.post("/api/v1/portal/admin/blog", json=blog_payload, headers=headers)
        assert resp.status_code == 201

        faq_payload = {"question": "How to adopt?", "answer": "Apply online", "category": "adoption", "is_published": True}
        resp = await client.post("/api/v1/portal/admin/faq", json=faq_payload, headers=headers)
        assert resp.status_code == 201

        vet_payload = {"name": "City Vet", "address": "456 Vet St", "phone": "+5678", "is_emergency": True, "is_active": True}
        resp = await client.post("/api/v1/portal/admin/veterinary-network", json=vet_payload, headers=headers)
        assert resp.status_code == 201

        contact_payload = {"name": "Main Shelter", "address": "789 Shelter Ave", "phone": "+9012", "operating_hours": "9-5 M-F"}
        resp = await client.post("/api/v1/portal/admin/contact", json=contact_payload, headers=headers)
        assert resp.status_code == 201

        setting_payload = {"value": "PawGuard Network", "description": "Org name"}
        resp = await client.put("/api/v1/portal/admin/settings/org_name", json=setting_payload, headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/portal/stats")
        assert resp.status_code == 200

        resp = await client.get("/api/v1/portal/success-stories")
        assert resp.status_code == 200

        resp = await client.get("/api/v1/portal/blog")
        assert resp.status_code == 200

        resp = await client.get("/api/v1/portal/faq")
        assert resp.status_code == 200

        resp = await client.get("/api/v1/portal/veterinary-network")
        assert resp.status_code == 200

        resp = await client.get("/api/v1/portal/contact")
        assert resp.status_code == 200

    async def test_fleet_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        veh_payload = {"make_model": "Toyota Hiace", "license_plate": f"AB-{uuid.uuid4().hex[:4].upper()}", "mileage": 1000, "status": "active"}
        resp = await client.post("/api/v1/fleet/vehicles", json=veh_payload, headers=headers)
        assert resp.status_code == 201
        veh_id = resp.json()["data"]["id"]

        maint_payload = {"vehicle_id": str(veh_id), "service_date": "2026-07-01", "description": "Oil change", "cost": 150.00}
        resp = await client.post("/api/v1/fleet/maintenance", json=maint_payload, headers=headers)
        assert resp.status_code == 201

    async def test_grievance_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        complaint_payload = {"reporter_name": "Public User", "reporter_phone": "+112233", "complaint_type": "service_delay", "details": "Rescue took too long"}
        resp = await client.post("/api/v1/grievance", json=complaint_payload)
        assert resp.status_code == 201
        ticket_id = resp.json()["data"]["id"]

        resp = await client.get("/api/v1/grievance", headers=headers)
        assert resp.status_code == 200

        update_payload = {"status": "investigating", "resolution_notes": "Looking into it"}
        resp = await client.put(f"/api/v1/grievance/{ticket_id}", json=update_payload, headers=headers)
        assert resp.status_code == 200

        fb_payload = {"rating": 5, "comments": "Great service"}
        resp = await client.post("/api/v1/grievance/feedback", json=fb_payload)
        assert resp.status_code == 201

    async def test_notification_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.get("/api/v1/notifications", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
        assert resp.status_code == 200

        resp = await client.put("/api/v1/notifications/read-all", headers=headers)
        assert resp.status_code == 200

    async def test_audit_log_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.get("/api/v1/admin/audit-logs", headers=headers)
        assert resp.status_code == 200

    async def test_profile_update(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.put("/api/v1/auth/me", json={"full_name": "Updated Name", "phone": "+999"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["full_name"] == "Updated Name"

    async def test_dashboard_summary(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.get("/api/v1/admin/dashboard/summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_users" in data
        assert "total_dogs" in data

        resp = await client.get("/api/v1/admin/dashboard/kpis", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/admin/dashboard/metrics", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/admin/dashboard/shelter-stats", headers=headers)
        assert resp.status_code == 200

    async def test_dashboard_inventory_alerts(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.get("/api/v1/admin/dashboard/inventory-alerts", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/admin/dashboard/donation-summary", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/admin/dashboard/recent-activity", headers=headers)
        assert resp.status_code == 200

    async def test_dashboard_stats(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        for ep in ["rescue-stats", "medical-stats", "adoption-stats", "volunteer-stats"]:
            resp = await client.get(f"/api/v1/admin/dashboard/{ep}", headers=headers)
            assert resp.status_code == 200, f"{ep} failed"

    async def test_settings_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.get("/api/v1/settings/general", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/settings/email", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/settings/storage", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/settings/password-policy", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/settings/system", headers=headers)
        assert resp.status_code == 200

    async def test_settings_crud(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        create_resp = await client.post(
            "/api/v1/settings/system",
            json={"key": "test.setting", "value": "test_val", "category": "test"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        setting_id = create_resp.json()["data"]["id"]

        get_resp = await client.get("/api/v1/settings/system/test.setting", headers=headers)
        assert get_resp.status_code == 200

        update_resp = await client.put(
            "/api/v1/settings/system/test.setting",
            json={"value": "updated_val"},
            headers=headers,
        )
        assert update_resp.status_code == 200

        delete_resp = await client.delete(f"/api/v1/settings/system/{setting_id}", headers=headers)
        assert delete_resp.status_code == 204

    async def test_business_rules_crud(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        create_resp = await client.post(
            "/api/v1/settings/business-rules",
            json={"rule_key": "rescue.max_distance_km", "rule_value": "50", "module": "rescue"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["data"]["id"]

        resp = await client.get("/api/v1/settings/business-rules", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/settings/business-rules/rescue.max_distance_km", headers=headers)
        assert resp.status_code == 200

        delete_resp = await client.delete(f"/api/v1/settings/business-rules/{rule_id}", headers=headers)
        assert delete_resp.status_code == 204

    async def test_notification_preferences(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.get("/api/v1/notifications/preferences", headers=headers)
        assert resp.status_code == 200

        resp = await client.put(
            "/api/v1/notifications/preferences",
            json={"enable_sms": True, "enable_push": False},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["enable_sms"] is True
        assert resp.json()["data"]["enable_push"] is False

    async def test_notification_mark_read(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.put("/api/v1/notifications/read-all", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
        assert resp.status_code == 200

    async def test_finance_chart_of_accounts_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        payload = {"account_code": "1010", "account_name": "Cash", "account_type": "asset", "category": "cash"}
        resp = await client.post("/api/v1/finance/accounts", json=payload, headers=headers)
        assert resp.status_code == 201
        acct_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/finance/accounts/{acct_id}", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/finance/accounts", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1

        resp = await client.put(f"/api/v1/finance/accounts/{acct_id}", json={"account_name": "Petty Cash"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["account_name"] == "Petty Cash"

        resp = await client.delete(f"/api/v1/finance/accounts/{acct_id}", headers=headers)
        assert resp.status_code == 200

    async def test_finance_transaction_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        debit = await client.post("/api/v1/finance/accounts", json={"account_code": "5010", "account_name": "Expense A", "account_type": "expense", "category": "supplies_expense"}, headers=headers)
        assert debit.status_code == 201
        debit_id = debit.json()["data"]["id"]
        credit = await client.post("/api/v1/finance/accounts", json={"account_code": "1011", "account_name": "Bank", "account_type": "asset", "category": "bank"}, headers=headers)
        credit_id = credit.json()["data"]["id"]

        tx_payload = {
            "transaction_type": "expense", "transaction_date": "2026-07-30",
            "amount": 500.00, "debit_account_id": debit_id, "credit_account_id": credit_id,
        }
        resp = await client.post("/api/v1/finance/transactions", json=tx_payload, headers=headers)
        assert resp.status_code == 201
        tx_id = resp.json()["data"]["id"]
        assert resp.json()["data"]["transaction_number"].startswith("TXN-")

        resp = await client.get(f"/api/v1/finance/transactions/{tx_id}", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/finance/transactions", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/finance/account-balances", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/finance/summary?period_start=2026-01-01&period_end=2026-12-31", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/v1/finance/pnl?period_start=2026-01-01&period_end=2026-12-31", headers=headers)
        assert resp.status_code == 200

    async def test_finance_budget_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        acct = await client.post("/api/v1/finance/accounts", json={"account_code": "6010", "account_name": "Supplies", "account_type": "expense", "category": "supplies_expense"}, headers=headers)
        acct_id = acct.json()["data"]["id"]

        budget_payload = {"name": "Annual 2026", "fiscal_year": 2026, "start_date": "2026-01-01", "end_date": "2026-12-31"}
        resp = await client.post("/api/v1/finance/budgets", json=budget_payload, headers=headers)
        assert resp.status_code == 201
        budget_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/finance/budgets/{budget_id}", headers=headers)
        assert resp.status_code == 200

        item_payload = {"account_id": acct_id, "allocated_amount": 10000}
        resp = await client.post(f"/api/v1/finance/budgets/{budget_id}/items", json=item_payload, headers=headers)
        assert resp.status_code == 201

        resp = await client.get("/api/v1/finance/budgets", headers=headers)
        assert resp.status_code == 200

        resp = await client.delete(f"/api/v1/finance/budgets/{budget_id}", headers=headers)
        assert resp.status_code == 200

    async def test_finance_recurring_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        debit = await client.post("/api/v1/finance/accounts", json={"account_code": "7010", "account_name": "Rent Exp", "account_type": "expense", "category": "supplies_expense"}, headers=headers)
        credit = await client.post("/api/v1/finance/accounts", json={"account_code": "1012", "account_name": "Bank B", "account_type": "asset", "category": "bank"}, headers=headers)

        payload = {
            "name": "Monthly Rent", "transaction_type": "expense", "amount": 2000.00,
            "interval": "monthly", "start_date": "2026-01-01",
            "debit_account_id": debit.json()["data"]["id"],
            "credit_account_id": credit.json()["data"]["id"],
        }
        resp = await client.post("/api/v1/finance/recurring", json=payload, headers=headers)
        assert resp.status_code == 201

        resp = await client.get("/api/v1/finance/recurring", headers=headers)
        assert resp.status_code == 200

    async def test_reports_generate_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        resp = await client.get("/api/v1/reports/types", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 10

        resp = await client.get("/api/v1/reports/formats", headers=headers)
        assert resp.status_code == 200

        payload = {"report_type": "donation", "format": "csv"}
        resp = await client.post("/api/v1/reports/generate", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["format"] == "csv"
        assert "filename" in data
        assert "download_url" in data

        filename = data["filename"]
        resp = await client.get(f"/api/v1/reports/download/{filename}", headers=headers)
        assert resp.status_code == 200

    async def test_reports_multiple_formats(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        for fmt in ["pdf", "csv", "xlsx"]:
            payload = {"report_type": "adoption", "format": fmt}
            resp = await client.post("/api/v1/reports/generate", json=payload, headers=headers)
            assert resp.status_code == 200, f"{fmt} failed: {resp.text}"
            assert resp.json()["data"]["format"] == fmt

    async def test_reports_with_period_filter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        payload = {
            "report_type": "medical",
            "format": "csv",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        }
        resp = await client.post("/api/v1/reports/generate", json=payload, headers=headers)
        assert resp.status_code == 200

    async def test_dashboards_all_role_endpoints(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await self._auth(client, db_session)

        endpoints = [
            ("rescue", "/api/v1/dashboards/rescue"),
            ("shelter", "/api/v1/dashboards/shelter"),
            ("medical", "/api/v1/dashboards/medical"),
            ("adoption", "/api/v1/dashboards/adoption"),
            ("foster", "/api/v1/dashboards/foster"),
            ("volunteer", "/api/v1/dashboards/volunteer"),
            ("inventory", "/api/v1/dashboards/inventory"),
            ("finance", "/api/v1/dashboards/finance"),
            ("donor", "/api/v1/dashboards/donor"),
            ("staff", "/api/v1/dashboards/staff"),
            ("executive", "/api/v1/dashboards/executive"),
            ("public", "/api/v1/dashboards/public"),
            ("operations", "/api/v1/dashboards/operations"),
        ]
        for name, url in endpoints:
            resp = await client.get(url, headers=headers)
            assert resp.status_code == 200, f"{name} dashboard failed: {resp.text}"
            data = resp.json()["data"]
            assert isinstance(data, dict), f"{name} dashboard returned non-dict: {type(data)}"
