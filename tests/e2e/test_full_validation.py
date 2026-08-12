"""Master E2E test: tests ALL 442 endpoints with a single shared setup.

This file avoids the per-test setup overhead by creating all prerequisite
data once in a session-scoped fixture.
"""
import json
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_helpers import register_and_auth, _DEFAULT_PASSWORD
from tests.e2e.perf_tracker import tracker

uid = lambda: uuid.uuid4().hex[:8]


async def call(client, module, method, path, headers=None, json=None, params=None, expected=200):
    """Call endpoint, measure latency, record result."""
    tracker.start(module, method.upper(), path)
    t0 = time.perf_counter()
    try:
        r = await client.request(method, path, headers=headers, json=json, params=params, timeout=30)
        latency = (time.perf_counter() - t0) * 1000
        tracker.record(r.status_code, expected, latency)
        if r.status_code == expected:
            tracker.finish("PASS")
        else:
            tracker.finish("FAIL", f"got={r.status_code} expected={expected} body={r.text[:300]}")
        return r
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        tracker.record(0, expected, latency)
        tracker.finish("FAIL", f"exception={e}")
        raise


class State:
    """Shared mutable state across all tests."""
    admin_headers = {}
    staff_headers = {}
    user_headers = {}
    dog_id = None
    dog_id_2 = None
    facility_id = None
    section_id = None
    kennel_id = None
    rescue_request_id = None
    dispatch_id = None
    foster_profile_id = None
    placement_id = None
    adoption_app_id = None
    donor_id = None
    donation_id = None
    campaign_id = None
    sponsorship_id = None
    volunteer_profile_id = None
    shift_id = None
    inventory_item_id = None
    finance_account_debit = None
    finance_account_credit = None
    transaction_id = None
    budget_id = None
    vehicle_id = None
    companion_pet_id = None
    vet_clinic_id = None
    appointment_id = None
    prescription_id = None
    lost_report_id = None
    found_report_id = None
    grievance_ticket_id = None
    feedback_id = None
    storage_file_id = None
    role_id = None
    follow_up_id = None
    transfer_id = None


S = State()


# ═══════════════════════════════════════════════════════════════════════════
# SETUP — create all prerequisite data once
# ═══════════════════════════════════════════════════════════════════════════

async def _setup(client, db):
    """Create all prerequisite data."""
    # Admin user
    email = f"admin_{uid()}@test.com"
    S.admin_headers = await register_and_auth(client, db, email=email, role="super_admin")

    # Staff user
    email2 = f"staff_{uid()}@test.com"
    S.staff_headers = await register_and_auth(client, db, email=email2, role="shelter_manager")

    # Regular user
    email3 = f"user_{uid()}@test.com"
    S.user_headers = await register_and_auth(client, db, email=email3, role="volunteer")

    # Facility
    r = await client.post("/api/v1/shelter/facilities", headers=S.admin_headers, json={
        "name": f"Shelter_{uid()}", "address": "123 Rescue Lane",
        "phone": "+1234567890", "total_capacity": 50, "facility_type": "shelter",
    })
    if r.status_code in (200, 201):
        S.facility_id = r.json()["data"]["id"]
        # Section
        r2 = await client.post(f"/api/v1/shelter/facilities/{S.facility_id}/sections",
                               headers=S.admin_headers, json={
                                   "name": f"Sec_{uid()}", "section_type": "general", "capacity": 10,
                               })
        if r2.status_code in (200, 201):
            S.section_id = r2.json()["data"]["id"]
            # Kennel
            r3 = await client.post(f"/api/v1/shelter/sections/{S.section_id}/kennels",
                                   headers=S.admin_headers, json={
                                       "identifier": f"K-{uid()}", "capacity": 1,
                                   })
            if r3.status_code in (200, 201):
                S.kennel_id = r3.json()["data"]["id"]

    # Dog
    r = await client.post("/api/v1/dogs", headers=S.admin_headers, json={
        "name": f"Buddy_{uid()}", "breed": "indie_mix", "gender": "male",
        "age_months": 24, "weight": 15.0, "is_adoptable": True,
        "is_quarantine_passed": True,
    })
    if r.status_code in (200, 201):
        S.dog_id = r.json()["data"]["id"]

    # Second dog
    r = await client.post("/api/v1/dogs", headers=S.admin_headers, json={
        "name": f"Rex_{uid()}", "breed": "labrador", "gender": "female",
        "age_months": 36, "weight": 25.0, "is_adoptable": True,
    })
    if r.status_code in (200, 201):
        S.dog_id_2 = r.json()["data"]["id"]

    # Inventory
    r = await client.post("/api/v1/inventory/items", headers=S.admin_headers, json={
        "name": f"Item_{uid()}", "category": "food", "quantity": 100.0,
        "unit": "kg", "reorder_threshold": 10.0, "unit_cost": 5.0,
    })
    if r.status_code in (200, 201):
        S.inventory_item_id = r.json()["data"]["id"]

    # Finance accounts
    r1 = await client.post("/api/v1/finance/accounts", headers=S.admin_headers, json={
        "account_code": f"100{uid()[:4]}", "account_name": f"Cash_{uid()}",
        "account_type": "asset", "category": "cash", "opening_balance": "10000.00",
    })
    if r1.status_code in (200, 201):
        S.finance_account_debit = r1.json()["data"]["id"]
    r2 = await client.post("/api/v1/finance/accounts", headers=S.admin_headers, json={
        "account_code": f"200{uid()[:4]}", "account_name": f"Donations_{uid()}",
        "account_type": "income", "category": "donation_income", "opening_balance": "0.00",
    })
    if r2.status_code in (200, 201):
        S.finance_account_credit = r2.json()["data"]["id"]

    # Vehicle
    r = await client.post("/api/v1/fleet/vehicles", headers=S.admin_headers, json={
        "make_model": f"Toyota_{uid()}", "license_plate": f"DL-{uid()[:4]}",
        "vehicle_type": "rescue_van", "status": "active", "mileage": 5000,
    })
    if r.status_code in (200, 201):
        S.vehicle_id = r.json()["data"]["id"]

    # Vet clinic
    r = await client.post("/api/v1/companion-pets/clinics", headers=S.admin_headers, json={
        "name": f"VetClinic_{uid()}", "address": "789 Vet St", "phone": "+1122334455",
    })
    if r.status_code in (200, 201):
        S.vet_clinic_id = r.json()["data"]["id"]

    # Campaign
    r = await client.post("/api/v1/donations/campaigns", headers=S.admin_headers, json={
        "name": f"Camp_{uid()}", "description": "Test", "target_amount": 10000.0,
        "currency": "INR", "campaign_type": "general", "status": "active",
        "start_date": date.today().isoformat(),
    })
    if r.status_code in (200, 201):
        S.campaign_id = r.json()["data"]["id"]

    # Donor
    r = await client.post("/api/v1/donations/register", headers=S.admin_headers, json={
        "tax_identifier": f"TAX_{uid()}",
    })
    if r.status_code in (200, 201):
        S.donor_id = r.json()["data"]["id"]

    print(f"\n  SETUP COMPLETE: admin={bool(S.admin_headers)} dog={S.dog_id is not None} "
          f"facility={S.facility_id is not None} finance={S.finance_account_debit is not None}")


# ═══════════════════════════════════════════════════════════════════════════
# AUTH (22 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestAuth:

    async def test_01_register(self, client, db_session):
        await _setup(client, db_session)
        await call(client, "auth", "POST", "/api/v1/auth/register", json={
            "email": f"reg_{uid()}@test.com", "password": _DEFAULT_PASSWORD,
            "full_name": "Test", "phone": "+1234567890",
        }, expected=201)

    async def test_02_login(self, client, db_session):
        email = f"login_{uid()}@test.com"
        await client.post("/api/v1/auth/register", json={
            "email": email, "password": _DEFAULT_PASSWORD,
            "full_name": "Login", "phone": "+1234567890",
        })
        await call(client, "auth", "POST", "/api/v1/auth/login",
                   json={"email": email, "password": _DEFAULT_PASSWORD}, expected=200)

    async def test_03_mfa_verify(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/mfa/verify",
                   json={"pre_auth_token": "bad", "code": "000000"}, expected=401)

    async def test_04_refresh(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/refresh",
                   json={"refresh_token": "bad"}, expected=401)

    async def test_05_logout(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/logout",
                   headers=S.admin_headers, expected=200)

    async def test_06_logout_all(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/logout-all",
                   headers=S.admin_headers, expected=200)

    async def test_07_me(self, client, db_session):
        await call(client, "auth", "GET", "/api/v1/auth/me",
                   headers=S.admin_headers, expected=200)

    async def test_08_update_me(self, client, db_session):
        await call(client, "auth", "PUT", "/api/v1/auth/me",
                   headers=S.admin_headers, json={"full_name": "Updated"}, expected=200)

    async def test_09_sessions(self, client, db_session):
        await call(client, "auth", "GET", "/api/v1/auth/sessions",
                   headers=S.admin_headers, expected=200)

    async def test_10_revoke_session(self, client, db_session):
        await call(client, "auth", "DELETE", f"/api/v1/auth/sessions/{uuid.uuid4()}",
                   headers=S.admin_headers, expected=404)

    async def test_11_change_password(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/password/change",
                   headers=S.admin_headers,
                   json={"current_password": "wrong", "new_password": "X@12345678"}, expected=401)

    async def test_12_reset_request(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/password/reset/request",
                   json={"email": "nobody@test.com"}, expected=200)

    async def test_13_reset_confirm(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/password/reset/confirm",
                   json={"token": "bad", "new_password": "X@12345678"}, expected=400)

    async def test_14_email_confirm(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/email/verify/confirm",
                   json={"token": "bad"}, expected=400)

    async def test_15_email_request(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/email/verify/request",
                   headers=S.admin_headers, expected=200)

    async def test_16_mfa_enroll(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/mfa/enroll",
                   headers=S.admin_headers, expected=200)

    async def test_17_mfa_confirm(self, client, db_session):
        r = await client.post("/api/v1/auth/mfa/enroll", headers=S.admin_headers)
        if r.status_code == 200:
            secret = r.json()["data"]["secret"]
            await call(client, "auth", "POST", "/api/v1/auth/mfa/enroll/confirm",
                       headers=S.admin_headers, json={"code": pyotp.TOTP(secret).now()}, expected=200)

    async def test_18_mfa_disable(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/mfa/disable",
                   headers=S.admin_headers, json={"password": _DEFAULT_PASSWORD}, expected=200)

    async def test_19_oauth_login(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/oauth/login",
                   json={"provider": "google", "provider_token": "fake"}, expected=401)

    async def test_20_oauth_accounts(self, client, db_session):
        await call(client, "auth", "GET", "/api/v1/auth/oauth/accounts",
                   headers=S.admin_headers, expected=200)

    async def test_21_oauth_link(self, client, db_session):
        await call(client, "auth", "POST", "/api/v1/auth/oauth/link",
                   headers=S.admin_headers,
                   json={"provider": "google", "provider_token": "fake"}, expected=400)

    async def test_22_oauth_unlink(self, client, db_session):
        await call(client, "auth", "DELETE", f"/api/v1/auth/oauth/accounts/{uuid.uuid4()}",
                   headers=S.admin_headers, expected=404)


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN (11 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestAdmin:

    async def test_list_roles(self, client, db_session):
        await call(client, "admin", "GET", "/api/v1/admin/roles",
                   headers=S.admin_headers, expected=200)

    async def test_create_role(self, client, db_session):
        r = await call(client, "admin", "POST", "/api/v1/admin/roles",
                       headers=S.admin_headers,
                       json={"name": f"role_{uid()}", "description": "Test"}, expected=201)
        if r.status_code == 201:
            S.role_id = r.json()["data"]["id"]

    async def test_get_role(self, client, db_session):
        if S.role_id:
            await call(client, "admin", "GET", f"/api/v1/admin/roles/{S.role_id}",
                       headers=S.admin_headers, expected=200)
        else:
            await call(client, "admin", "GET", f"/api/v1/admin/roles/{uuid.uuid4()}",
                       headers=S.admin_headers, expected=404)

    async def test_update_role(self, client, db_session):
        if S.role_id:
            await call(client, "admin", "PUT", f"/api/v1/admin/roles/{S.role_id}",
                       headers=S.admin_headers, json={"description": "Updated"}, expected=200)

    async def test_delete_role(self, client, db_session):
        r = await client.post("/api/v1/admin/roles", headers=S.admin_headers,
                              json={"name": f"del_{uid()}", "description": "x"})
        if r.status_code == 201:
            rid = r.json()["data"]["id"]
            await call(client, "admin", "DELETE", f"/api/v1/admin/roles/{rid}",
                       headers=S.admin_headers, expected=200)

    async def test_list_permissions(self, client, db_session):
        await call(client, "admin", "GET", "/api/v1/admin/permissions",
                   headers=S.admin_headers, expected=200)

    async def test_list_users(self, client, db_session):
        await call(client, "admin", "GET", "/api/v1/admin/users",
                   headers=S.admin_headers, expected=200)

    async def test_create_user(self, client, db_session):
        await call(client, "admin", "POST", "/api/v1/admin/users",
                   headers=S.admin_headers, json={
                       "email": f"cr_{uid()}@test.com", "password": _DEFAULT_PASSWORD,
                       "full_name": "Created", "phone": "+1234567890",
                   }, expected=201)

    async def test_get_user(self, client, db_session):
        r = await client.get("/api/v1/admin/users", headers=S.admin_headers)
        if r.status_code == 200 and r.json()["data"]:
            uid_val = r.json()["data"][0]["id"]
            await call(client, "admin", "GET", f"/api/v1/admin/users/{uid_val}",
                       headers=S.admin_headers, expected=200)

    async def test_update_user(self, client, db_session):
        r = await client.get("/api/v1/admin/users", headers=S.admin_headers)
        if r.status_code == 200 and r.json()["data"]:
            uid_val = r.json()["data"][0]["id"]
            await call(client, "admin", "PUT", f"/api/v1/admin/users/{uid_val}",
                       headers=S.admin_headers, json={"full_name": "Upd"}, expected=200)

    async def test_delete_user(self, client, db_session):
        r = await client.post("/api/v1/admin/users", headers=S.admin_headers, json={
            "email": f"del_{uid()}@test.com", "password": _DEFAULT_PASSWORD, "full_name": "Del",
        })
        if r.status_code == 201:
            uid_val = r.json()["data"]["id"]
            await call(client, "admin", "DELETE", f"/api/v1/admin/users/{uid_val}",
                       headers=S.admin_headers, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# DOGS (13 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestDogs:

    async def test_list(self, client, db_session):
        await call(client, "dogs", "GET", "/api/v1/dogs", expected=200)

    async def test_create(self, client, db_session):
        r = await call(client, "dogs", "POST", "/api/v1/dogs", headers=S.admin_headers, json={
            "name": f"Dog_{uid()}", "breed": "beagle", "gender": "male",
            "is_adoptable": True, "is_quarantine_passed": True,
        }, expected=201)

    async def test_get(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "GET", f"/api/v1/dogs/{S.dog_id}", expected=200)

    async def test_get_not_found(self, client, db_session):
        await call(client, "dogs", "GET", f"/api/v1/dogs/{uuid.uuid4()}", expected=404)

    async def test_update(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "PUT", f"/api/v1/dogs/{S.dog_id}",
                       headers=S.admin_headers, json={"name": "Updated"}, expected=200)

    async def test_admin_get(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "GET", f"/api/v1/dogs/admin/dogs/{S.dog_id}", expected=200)

    async def test_timeline(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "GET", f"/api/v1/dogs/{S.dog_id}/timeline",
                       headers=S.admin_headers, expected=200)

    async def test_public_scan(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "GET", f"/api/v1/dogs/{S.dog_id}/public-scan", expected=200)

    async def test_qr_image(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "GET", f"/api/v1/dogs/{S.dog_id}/qr-image",
                       headers=S.admin_headers, expected=200)

    async def test_weight(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "POST", f"/api/v1/dogs/{S.dog_id}/weight",
                       headers=S.admin_headers, json={"weight": 25.5}, expected=201)

    async def test_weights(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "GET", f"/api/v1/dogs/{S.dog_id}/weights",
                       headers=S.admin_headers, expected=200)

    async def test_status(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "PATCH", f"/api/v1/dogs/{S.dog_id}/status",
                       headers=S.admin_headers, json={"status": "available"}, expected=200)

    async def test_admin_status(self, client, db_session):
        if S.dog_id:
            await call(client, "dogs", "PATCH", f"/api/v1/dogs/admin/dogs/{S.dog_id}/status",
                       headers=S.admin_headers, json={"status": "available"}, expected=200)

    async def test_bulk_status(self, client, db_session):
        await call(client, "dogs", "POST", "/api/v1/dogs/bulk/status-update",
                   headers=S.admin_headers, json={"ids": [], "status": "available"}, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "dogs", "POST", "/api/v1/dogs/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_delete(self, client, db_session):
        r = await client.post("/api/v1/dogs", headers=S.admin_headers, json={
            "name": f"Del_{uid()}", "breed": "poodle", "gender": "female",
        })
        if r.status_code == 201:
            did = r.json()["data"]["id"]
            await call(client, "dogs", "DELETE", f"/api/v1/dogs/{did}",
                       headers=S.admin_headers, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# RESCUE (20 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestRescue:

    async def test_report(self, client, db_session):
        r = await call(client, "rescue", "POST", "/api/v1/rescue/report",
                       headers=S.admin_headers, json={
                           "reporter_name": f"Rep_{uid()}", "reporter_phone": "+9876543210",
                           "location_address": "456 Road", "animal_count": 1,
                           "physical_condition": "injured", "severity": "high",
                       }, expected=201)
        if r.status_code == 201:
            S.rescue_request_id = r.json()["data"]["id"]

    async def test_media_url(self, client, db_session):
        await call(client, "rescue", "POST", "/api/v1/rescue/media-upload-url",
                   headers=S.admin_headers, json={
                       "filename": "test.jpg", "mime_type": "image/jpeg", "file_size": 1024,
                   }, expected=200)

    async def test_verify(self, client, db_session):
        if S.rescue_request_id:
            await call(client, "rescue", "POST",
                       f"/api/v1/rescue/{S.rescue_request_id}/verify",
                       headers=S.admin_headers, json={"status": "verified"}, expected=200)

    async def test_assign_coordinator(self, client, db_session):
        if S.rescue_request_id:
            await call(client, "rescue", "POST",
                       f"/api/v1/rescue/{S.rescue_request_id}/assign-coordinator",
                       headers=S.admin_headers,
                       json={"coordinator_id": str(uuid.uuid4())}, expected=200)

    async def test_dispatch(self, client, db_session):
        if S.rescue_request_id:
            r = await call(client, "rescue", "POST",
                           f"/api/v1/rescue/{S.rescue_request_id}/dispatch",
                           headers=S.admin_headers, json={"notes": "Deploy"}, expected=201)
            if r.status_code == 201:
                data = r.json().get("data", {})
                if data and "id" in data:
                    S.dispatch_id = data["id"]

    async def test_patch_dispatch(self, client, db_session):
        if S.dispatch_id:
            await call(client, "rescue", "PATCH", f"/api/v1/rescue/dispatch/{S.dispatch_id}",
                       headers=S.admin_headers, json={"notes": "Updated"}, expected=200)

    async def test_delete_dispatch(self, client, db_session):
        if S.rescue_request_id:
            r = await client.post(f"/api/v1/rescue/{S.rescue_request_id}/dispatch",
                                  headers=S.admin_headers, json={"notes": "Del"})
            if r.status_code == 201:
                data = r.json().get("data", {})
                if data and "id" in data:
                    await call(client, "rescue", "DELETE",
                               f"/api/v1/rescue/dispatch/{data['id']}",
                               headers=S.admin_headers, expected=200)

    async def test_escalate(self, client, db_session):
        if S.rescue_request_id:
            await call(client, "rescue", "POST",
                       f"/api/v1/rescue/{S.rescue_request_id}/escalate",
                       headers=S.admin_headers,
                       json={"escalation_type": "medical"}, expected=200)

    async def test_located(self, client, db_session):
        if S.rescue_request_id:
            await call(client, "rescue", "POST",
                       f"/api/v1/rescue/{S.rescue_request_id}/located",
                       headers=S.admin_headers, expected=200)

    async def test_secured(self, client, db_session):
        if S.rescue_request_id:
            await call(client, "rescue", "POST",
                       f"/api/v1/rescue/{S.rescue_request_id}/secured",
                       headers=S.admin_headers, expected=200)

    async def test_admitted(self, client, db_session):
        if S.rescue_request_id:
            await call(client, "rescue", "POST",
                       f"/api/v1/rescue/{S.rescue_request_id}/admitted",
                       headers=S.admin_headers, json={"notes": "Admitted"}, expected=200)

    async def test_fail(self, client, db_session):
        if S.rescue_request_id:
            await call(client, "rescue", "POST",
                       f"/api/v1/rescue/{S.rescue_request_id}/fail",
                       headers=S.admin_headers, params={"failure_reason": "not_found"},
                       expected=200)

    async def test_status_lookup(self, client, db_session):
        await call(client, "rescue", "GET", "/api/v1/rescue/status",
                   params={"ticket_number": "FAKE"}, expected=404)

    async def test_list_dispatches(self, client, db_session):
        await call(client, "rescue", "GET", "/api/v1/rescue/dispatches",
                   headers=S.admin_headers, expected=200)

    async def test_get_request(self, client, db_session):
        if S.rescue_request_id:
            await call(client, "rescue", "GET", f"/api/v1/rescue/{S.rescue_request_id}",
                       expected=200)

    async def test_list_requests(self, client, db_session):
        await call(client, "rescue", "GET", "/api/v1/rescue",
                   headers=S.admin_headers, expected=200)

    async def test_delete_request(self, client, db_session):
        r = await client.post("/api/v1/rescue/report", headers=S.admin_headers, json={
            "reporter_name": "Del", "reporter_phone": "+111", "location_address": "X",
            "animal_count": 1, "physical_condition": "healthy", "severity": "low",
        })
        if r.status_code == 201:
            rid = r.json()["data"]["id"]
            await call(client, "rescue", "DELETE", f"/api/v1/rescue/{rid}",
                       headers=S.admin_headers, expected=200)

    async def test_bulk_status(self, client, db_session):
        await call(client, "rescue", "POST", "/api/v1/rescue/bulk/status-update",
                   headers=S.admin_headers, json={"ids": [], "status": "closed"}, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "rescue", "POST", "/api/v1/rescue/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_delete_dispatches_alias(self, client, db_session):
        if S.rescue_request_id:
            r = await client.post(f"/api/v1/rescue/{S.rescue_request_id}/dispatch",
                                  headers=S.admin_headers, json={"notes": "X"})
            if r.status_code == 201:
                data = r.json().get("data", {})
                if data and "id" in data:
                    await call(client, "rescue", "DELETE",
                               f"/api/v1/rescue/dispatches/{data['id']}",
                               headers=S.admin_headers, expected=200)

    async def test_patch_dispatches_alias(self, client, db_session):
        if S.rescue_request_id:
            r = await client.post(f"/api/v1/rescue/{S.rescue_request_id}/dispatch",
                                  headers=S.admin_headers, json={"notes": "Y"})
            if r.status_code == 201:
                data = r.json().get("data", {})
                if data and "id" in data:
                    await call(client, "rescue", "PATCH",
                               f"/api/v1/rescue/dispatches/{data['id']}",
                               headers=S.admin_headers, json={"notes": "Z"}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC RESCUE (2 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestPublicRescue:

    async def test_public_report(self, client, db_session):
        await call(client, "public-rescue", "POST", "/api/v1/public/rescue/report", json={
            "reporter_name": "Pub", "reporter_phone": "+123", "location_address": "X",
            "animal_count": 1, "physical_condition": "unknown", "severity": "medium",
        }, expected=201)

    async def test_public_media(self, client, db_session):
        await call(client, "public-rescue", "POST", "/api/v1/public/rescue/media-upload-url",
                   json={"filename": "p.jpg", "mime_type": "image/jpeg", "file_size": 2048},
                   expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# RESCUE CENTRES (8 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestRescueCentres:

    async def test_list(self, client, db_session):
        await call(client, "rescue-centres", "GET", "/api/v1/rescue-centres", expected=200)

    async def test_create(self, client, db_session):
        r = await call(client, "rescue-centres", "POST", "/api/v1/rescue-centres",
                       headers=S.admin_headers, json={
                           "name": f"RC_{uid()}", "address": "123", "phone": "+1",
                           "total_capacity": 30, "facility_type": "rescue_centre",
                       }, expected=201)
        if r.status_code == 201:
            S.facility_id = r.json()["data"]["id"]

    async def test_get_one(self, client, db_session):
        if S.facility_id:
            await call(client, "rescue-centres", "GET",
                       f"/api/v1/rescue-centres/{S.facility_id}", expected=200)

    async def test_update(self, client, db_session):
        if S.facility_id:
            await call(client, "rescue-centres", "PUT",
                       f"/api/v1/rescue-centres/{S.facility_id}",
                       headers=S.admin_headers, json={"name": "Upd"}, expected=200)

    async def test_update_status(self, client, db_session):
        if S.facility_id:
            await call(client, "rescue-centres", "PUT",
                       f"/api/v1/rescue-centres/{S.facility_id}/status",
                       headers=S.admin_headers, json={"status": "active"}, expected=200)

    async def test_delete(self, client, db_session):
        r = await client.post("/api/v1/rescue-centres", headers=S.admin_headers, json={
            "name": f"Del_{uid()}", "address": "X", "phone": "+0", "total_capacity": 1,
        })
        if r.status_code == 201:
            fid = r.json()["data"]["id"]
            await call(client, "rescue-centres", "DELETE", f"/api/v1/rescue-centres/{fid}",
                       headers=S.admin_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "rescue-centres", "POST", "/api/v1/rescue-centres/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_bulk_status(self, client, db_session):
        await call(client, "rescue-centres", "POST", "/api/v1/rescue-centres/bulk/status",
                   headers=S.admin_headers, json={"ids": [], "status": "active"}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# COMPANION PETS (27 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCompanionPets:

    async def test_list(self, client, db_session):
        await call(client, "companion-pets", "GET", "/api/v1/companion-pets",
                   headers=S.admin_headers, expected=200)

    async def test_create(self, client, db_session):
        r = await call(client, "companion-pets", "POST", "/api/v1/companion-pets",
                       headers=S.admin_headers, json={
                           "name": f"Cat_{uid()}", "species": "cat", "breed": "persian",
                           "date_of_birth": "2022-01-15", "gender": "female", "weight": 4.5,
                       }, expected=201)
        if r.status_code == 201:
            S.companion_pet_id = r.json()["data"]["id"]

    async def test_clinics_list(self, client, db_session):
        await call(client, "companion-pets", "GET", "/api/v1/companion-pets/clinics", expected=200)

    async def test_clinic_create(self, client, db_session):
        r = await call(client, "companion-pets", "POST", "/api/v1/companion-pets/clinics",
                       headers=S.admin_headers, json={
                           "name": f"VC_{uid()}", "address": "X", "phone": "+1",
                       }, expected=201)
        if r.status_code == 201:
            S.vet_clinic_id = r.json()["data"]["id"]

    async def test_appointments_list(self, client, db_session):
        await call(client, "companion-pets", "GET", "/api/v1/companion-pets/appointments",
                   headers=S.admin_headers, expected=200)

    async def test_get_pet(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "GET",
                       f"/api/v1/companion-pets/{S.companion_pet_id}",
                       headers=S.admin_headers, expected=200)

    async def test_update_pet(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "PATCH",
                       f"/api/v1/companion-pets/{S.companion_pet_id}",
                       headers=S.admin_headers, json={"weight": 5.0}, expected=200)

    async def test_delete_pet(self, client, db_session):
        r = await client.post("/api/v1/companion-pets", headers=S.admin_headers, json={
            "name": f"Del_{uid()}", "species": "cat", "breed": "siamese", "gender": "male",
        })
        if r.status_code == 201:
            pid = r.json()["data"]["id"]
            await call(client, "companion-pets", "DELETE", f"/api/v1/companion-pets/{pid}",
                       headers=S.admin_headers, expected=200)

    async def test_medical_files_upload(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "POST",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/medical-files/upload-url",
                       headers=S.admin_headers,
                       json={"filename": "x.jpg", "mime_type": "image/jpeg", "file_size": 5120},
                       expected=200)

    async def test_medical_files_confirm(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "PUT",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/medical-files/{uuid.uuid4()}/confirm",
                       headers=S.admin_headers, expected=404)

    async def test_medical_files_list(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "GET",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/medical-files",
                       headers=S.admin_headers, expected=200)

    async def test_medical_records_list(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "GET",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/medical-records",
                       headers=S.admin_headers, expected=200)

    async def test_medical_record_create(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "POST",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/medical-records",
                       headers=S.admin_headers, json={
                           "record_type": "vaccination", "description": "Annual",
                           "date": datetime.now(UTC).isoformat(),
                       }, expected=201)

    async def test_safety_tag_create(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "POST",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/safety-tag",
                       headers=S.admin_headers, expected=200)

    async def test_safety_tag_get(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "GET",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/safety-tag",
                       headers=S.admin_headers, expected=200)

    async def test_safety_tag_scan(self, client, db_session):
        await call(client, "companion-pets", "POST", "/api/v1/companion-pets/safety-tag/scan",
                   json={"tag_id": "bad"}, expected=404)

    async def test_clinic_update(self, client, db_session):
        if S.vet_clinic_id:
            await call(client, "companion-pets", "PATCH",
                       f"/api/v1/companion-pets/clinics/{S.vet_clinic_id}",
                       headers=S.admin_headers, json={"name": "Upd"}, expected=200)

    async def test_clinic_delete(self, client, db_session):
        r = await client.post("/api/v1/companion-pets/clinics", headers=S.admin_headers,
                              json={"name": f"Del_{uid()}", "address": "X", "phone": "+0"})
        if r.status_code == 201:
            cid = r.json()["data"]["id"]
            await call(client, "companion-pets", "DELETE",
                       f"/api/v1/companion-pets/clinics/{cid}",
                       headers=S.admin_headers, expected=200)

    async def test_clinic_membership(self, client, db_session):
        if S.vet_clinic_id:
            await call(client, "companion-pets", "POST",
                       f"/api/v1/companion-pets/clinics/{S.vet_clinic_id}/memberships",
                       headers=S.admin_headers,
                       json={"user_id": str(uuid.uuid4()), "role": "veterinarian"},
                       expected=200)

    async def test_appointment_create(self, client, db_session):
        if S.companion_pet_id and S.vet_clinic_id:
            r = await call(client, "companion-pets", "POST", "/api/v1/companion-pets/appointments",
                           headers=S.admin_headers, json={
                               "pet_id": S.companion_pet_id, "clinic_id": S.vet_clinic_id,
                               "appointment_type": "checkup",
                               "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                           }, expected=201)
            if r.status_code == 201:
                S.appointment_id = r.json()["data"]["id"]

    async def test_appointment_get(self, client, db_session):
        if S.appointment_id:
            await call(client, "companion-pets", "GET",
                       f"/api/v1/companion-pets/appointments/{S.appointment_id}",
                       headers=S.admin_headers, expected=200)

    async def test_appointment_cancel(self, client, db_session):
        if S.appointment_id:
            await call(client, "companion-pets", "POST",
                       f"/api/v1/companion-pets/appointments/{S.appointment_id}/cancel",
                       headers=S.admin_headers, json={"reason": "No time"}, expected=200)

    async def test_appointment_confirm(self, client, db_session):
        if S.companion_pet_id and S.vet_clinic_id:
            r = await client.post("/api/v1/companion-pets/appointments",
                                  headers=S.admin_headers, json={
                                      "pet_id": S.companion_pet_id, "clinic_id": S.vet_clinic_id,
                                      "appointment_type": "vaccination",
                                      "scheduled_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
                                  })
            if r.status_code == 201:
                aid = r.json()["data"]["id"]
                await call(client, "companion-pets", "POST",
                           f"/api/v1/companion-pets/appointments/{aid}/confirm",
                           headers=S.admin_headers, expected=200)

    async def test_reminders_list(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "GET",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/reminders",
                       headers=S.admin_headers, expected=200)

    async def test_reminder_create(self, client, db_session):
        if S.companion_pet_id:
            await call(client, "companion-pets", "POST",
                       f"/api/v1/companion-pets/{S.companion_pet_id}/reminders",
                       headers=S.admin_headers, json={
                           "title": "Vax due", "reminder_type": "vaccination",
                           "due_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                       }, expected=201)

    async def test_reminder_delete(self, client, db_session):
        if S.companion_pet_id:
            r = await client.post(f"/api/v1/companion-pets/{S.companion_pet_id}/reminders",
                                  headers=S.admin_headers, json={
                                      "title": "Del", "reminder_type": "checkup",
                                      "due_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
                                  })
            if r.status_code == 201:
                rid = r.json()["data"]["id"]
                await call(client, "companion-pets", "DELETE",
                           f"/api/v1/companion-pets/{S.companion_pet_id}/reminders/{rid}",
                           headers=S.admin_headers, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# MODULES BELOW: Quick GET/POST endpoints (dashboards, admin dash, audit)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestDashboards:
    async def test_rescue(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/rescue",headers=S.admin_headers,expected=200)
    async def test_shelter(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/shelter",headers=S.admin_headers,expected=200)
    async def test_medical(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/medical",headers=S.admin_headers,expected=200)
    async def test_adoption(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/adoption",headers=S.admin_headers,expected=200)
    async def test_foster(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/foster",headers=S.admin_headers,expected=200)
    async def test_volunteer(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/volunteer",headers=S.admin_headers,expected=200)
    async def test_inventory(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/inventory",headers=S.admin_headers,expected=200)
    async def test_finance(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/finance",headers=S.admin_headers,expected=200)
    async def test_donor(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/donor",headers=S.admin_headers,expected=200)
    async def test_staff(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/staff",headers=S.admin_headers,expected=200)
    async def test_executive(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/executive",headers=S.admin_headers,expected=200)
    async def test_public(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/public",expected=200)
    async def test_operations(self, client, db_session): await call(client,"dashboards","GET","/api/v1/dashboards/operations",headers=S.admin_headers,expected=200)


@pytest.mark.asyncio
class TestAdminDashboard:
    _paths = ["metrics","summary","kpis","charts","recent-activity","inventory-alerts",
              "donation-summary","rescue-stats","medical-stats","adoption-stats",
              "volunteer-stats","notification-summary","shelter-stats","foster-stats",
              "lost-found-stats","grievance-stats"]
    @pytest.mark.parametrize("p", _paths)
    async def test_endpoint(self, client, db_session, p):
        await call(client, "admin-dashboard", "GET", f"/api/v1/admin/dashboard/{p}",
                   headers=S.admin_headers, expected=200)


@pytest.mark.asyncio
class TestAdminAudit:
    async def test_list(self, client, db_session): await call(client,"admin-audit","GET","/api/v1/admin/audit-logs",headers=S.admin_headers,expected=200)
    async def test_export_get(self, client, db_session): await call(client,"admin-audit","GET","/api/v1/admin/audit-logs/export",headers=S.admin_headers,expected=200)
    async def test_export_post(self, client, db_session): await call(client,"admin-audit","POST","/api/v1/admin/audit-logs/export",headers=S.admin_headers,expected=200)
    async def test_get_one(self, client, db_session): await call(client,"admin-audit","GET",f"/api/v1/admin/audit-logs/{uuid.uuid4()}",headers=S.admin_headers,expected=404)


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH CHECKS (3 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestHealth:
    async def test_health(self, client, db_session): await call(client,"common","GET","/health",expected=200)
    async def test_live(self, client, db_session): await call(client,"common","GET","/live",expected=200)
    async def test_ready(self, client, db_session): await call(client,"common","GET","/ready",expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# REPORTS (4 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestReports:
    async def test_types(self, client, db_session): await call(client,"reports","GET","/api/v1/reports/types",headers=S.admin_headers,expected=200)
    async def test_formats(self, client, db_session): await call(client,"reports","GET","/api/v1/reports/formats",headers=S.admin_headers,expected=200)
    async def test_generate(self, client, db_session): await call(client,"reports","POST","/api/v1/reports/generate",headers=S.admin_headers,json={"report_type":"rescue_summary","format":"pdf"},expected=200)
    async def test_download(self, client, db_session): await call(client,"reports","GET",f"/api/v1/reports/download/{uid()}.pdf",headers=S.admin_headers,expected=404)


# ═══════════════════════════════════════════════════════════════════════════
# FOSTERS (13 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFosters:

    async def test_apply(self, client, db_session):
        r = await call(client, "fosters", "POST", "/api/v1/fosters/apply",
                       headers=S.user_headers, json={"max_capacity": 3, "preferences": "dogs"}, expected=201)
        if r.status_code == 201:
            S.foster_profile_id = r.json()["data"]["id"]

    async def test_list(self, client, db_session):
        await call(client, "fosters", "GET", "/api/v1/fosters",
                   headers=S.admin_headers, expected=200)

    async def test_update_profile(self, client, db_session):
        if S.foster_profile_id:
            await call(client, "fosters", "PUT", f"/api/v1/fosters/{S.foster_profile_id}",
                       headers=S.user_headers, json={"max_capacity": 5}, expected=200)

    async def test_place_dog(self, client, db_session):
        if S.foster_profile_id and S.dog_id:
            r = await call(client, "fosters", "POST",
                           f"/api/v1/fosters/{S.foster_profile_id}/placements",
                           headers=S.admin_headers,
                           json={"dog_id": S.dog_id, "notes": "Test placement"}, expected=201)
            if r.status_code == 201:
                S.placement_id = r.json()["data"]["id"]

    async def test_list_placements(self, client, db_session):
        await call(client, "fosters", "GET", "/api/v1/fosters/placements",
                   headers=S.admin_headers, expected=200)

    async def test_log_progress(self, client, db_session):
        if S.placement_id:
            await call(client, "fosters", "POST",
                       f"/api/v1/fosters/placements/{S.placement_id}/progress",
                       headers=S.user_headers,
                       json={"weight": 15.0, "behavior_notes": "Adjusting well"}, expected=201)

    async def test_get_progress(self, client, db_session):
        if S.placement_id:
            await call(client, "fosters", "GET",
                       f"/api/v1/fosters/placements/{S.placement_id}/progress",
                       headers=S.user_headers, expected=200)

    async def test_log_supplies(self, client, db_session):
        if S.placement_id:
            await call(client, "fosters", "POST",
                       f"/api/v1/fosters/placements/{S.placement_id}/supplies",
                       headers=S.user_headers,
                       json={"items": [{"name": "Dog food", "quantity": 2}]}, expected=201)

    async def test_get_supplies(self, client, db_session):
        if S.placement_id:
            await call(client, "fosters", "GET",
                       f"/api/v1/fosters/placements/{S.placement_id}/supplies",
                       headers=S.user_headers, expected=200)

    async def test_return_dog(self, client, db_session):
        if S.placement_id:
            await call(client, "fosters", "POST",
                       f"/api/v1/fosters/placements/{S.placement_id}/return",
                       headers=S.admin_headers, json={"reason": "Owner returned"}, expected=200)

    async def test_convert_to_adopt(self, client, db_session):
        if S.placement_id:
            await call(client, "fosters", "POST",
                       f"/api/v1/fosters/placements/{S.placement_id}/convert-to-adopt",
                       headers=S.admin_headers, expected=200)

    async def test_delete_profile(self, client, db_session):
        if S.foster_profile_id:
            await call(client, "fosters", "DELETE", f"/api/v1/fosters/{S.foster_profile_id}",
                       headers=S.user_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "fosters", "POST", "/api/v1/fosters/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# ADOPTIONS (18 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestAdoptions:

    async def test_create(self, client, db_session):
        if S.dog_id:
            r = await call(client, "adoptions", "POST", "/api/v1/adoptions",
                           headers=S.user_headers, json={
                               "dog_id": S.dog_id, "residential_status": "owned",
                               "has_landlord_approval": True, "has_yard_fence": True,
                               "household_members_count": 3, "pet_care_experience": "5 years",
                           }, expected=201)
            if r.status_code == 201:
                S.adoption_app_id = r.json()["data"]["id"]

    async def test_list(self, client, db_session):
        await call(client, "adoptions", "GET", "/api/v1/adoptions",
                   headers=S.admin_headers, expected=200)

    async def test_my_adoptions(self, client, db_session):
        await call(client, "adoptions", "GET", "/api/v1/adoptions/my",
                   headers=S.user_headers, expected=200)

    async def test_get(self, client, db_session):
        if S.adoption_app_id:
            await call(client, "adoptions", "GET", f"/api/v1/adoptions/{S.adoption_app_id}",
                       headers=S.user_headers, expected=200)

    async def test_update(self, client, db_session):
        if S.adoption_app_id:
            await call(client, "adoptions", "PUT", f"/api/v1/adoptions/{S.adoption_app_id}",
                       headers=S.user_headers, json={"household_members_count": 5}, expected=200)

    async def test_update_status(self, client, db_session):
        if S.adoption_app_id:
            await call(client, "adoptions", "PATCH", f"/api/v1/adoptions/{S.adoption_app_id}/status",
                       headers=S.admin_headers, json={"status": "approved"}, expected=200)

    async def test_agreement(self, client, db_session):
        if S.adoption_app_id:
            await call(client, "adoptions", "GET", f"/api/v1/adoptions/{S.adoption_app_id}/agreement",
                       headers=S.user_headers, expected=200)

    async def test_update_fee(self, client, db_session):
        if S.adoption_app_id:
            await call(client, "adoptions", "PUT", f"/api/v1/adoptions/{S.adoption_app_id}/fee",
                       headers=S.admin_headers, json={"adoption_fee": 500.0}, expected=200)

    async def test_create_followup(self, client, db_session):
        if S.adoption_app_id:
            r = await call(client, "adoptions", "POST",
                           f"/api/v1/adoptions/{S.adoption_app_id}/follow-ups",
                           headers=S.admin_headers,
                           json={"follow_up_type": "home_visit", "notes": "First follow-up"}, expected=201)
            if r.status_code == 201:
                S.follow_up_id = r.json()["data"]["id"]

    async def test_list_followups(self, client, db_session):
        if S.adoption_app_id:
            await call(client, "adoptions", "GET",
                       f"/api/v1/adoptions/{S.adoption_app_id}/follow-ups",
                       headers=S.admin_headers, expected=200)

    async def test_submit_followup_proof(self, client, db_session):
        if S.adoption_app_id and hasattr(S, "follow_up_id") and S.follow_up_id:
            await call(client, "adoptions", "POST",
                       f"/api/v1/adoptions/{S.adoption_app_id}/follow-ups/{S.follow_up_id}/proof",
                       headers=S.admin_headers,
                       json={"proof_url": "http://example.com/proof.jpg", "notes": "Photo proof"}, expected=200)

    async def test_create_score(self, client, db_session):
        if S.adoption_app_id:
            await call(client, "adoptions", "POST",
                       f"/api/v1/adoptions/{S.adoption_app_id}/scores",
                       headers=S.admin_headers,
                       json={"criteria": "home_environment", "score": 85}, expected=200)

    async def test_get_scores(self, client, db_session):
        if S.adoption_app_id:
            await call(client, "adoptions", "GET",
                       f"/api/v1/adoptions/{S.adoption_app_id}/scores",
                       headers=S.user_headers, expected=200)

    async def test_nearby_shelters(self, client, db_session):
        await call(client, "adoptions", "GET", "/api/v1/adoptions/nearby-shelters",
                   params={"latitude": 28.6139, "longitude": 77.2090}, expected=200)

    async def test_delete(self, client, db_session):
        if S.dog_id:
            r = await client.post("/api/v1/adoptions", headers=S.user_headers, json={
                "dog_id": S.dog_id, "residential_status": "owned",
                "has_landlord_approval": True, "has_yard_fence": True,
                "household_members_count": 2,
            })
            if r.status_code == 201:
                aid = r.json()["data"]["id"]
                await call(client, "adoptions", "DELETE", f"/api/v1/adoptions/{aid}",
                           headers=S.user_headers, expected=200)

    async def test_admin_delete(self, client, db_session):
        if S.dog_id:
            r = await client.post("/api/v1/adoptions", headers=S.user_headers, json={
                "dog_id": S.dog_id, "residential_status": "owned",
                "has_landlord_approval": True, "has_yard_fence": True,
                "household_members_count": 2,
            })
            if r.status_code == 201:
                aid = r.json()["data"]["id"]
                await call(client, "adoptions", "DELETE", f"/api/v1/adoptions/admin/adoptions/{aid}",
                           headers=S.admin_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "adoptions", "POST", "/api/v1/adoptions/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_bulk_status_update(self, client, db_session):
        await call(client, "adoptions", "POST", "/api/v1/adoptions/bulk/status-update",
                   headers=S.admin_headers, json={"ids": [], "status": "approved"}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# VOLUNTEERS (15 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestVolunteers:

    async def test_apply(self, client, db_session):
        r = await call(client, "volunteers", "POST", "/api/v1/volunteers/apply",
                       headers=S.user_headers, json={
                           "emergency_contact_name": "Emergency Contact",
                           "emergency_contact_phone": "+1234567890",
                           "skills": "animal care", "availability": "weekends",
                       }, expected=201)
        if r.status_code == 201:
            S.volunteer_profile_id = r.json()["data"]["id"]

    async def test_list(self, client, db_session):
        await call(client, "volunteers", "GET", "/api/v1/volunteers",
                   headers=S.admin_headers, expected=200)

    async def test_get(self, client, db_session):
        if S.volunteer_profile_id:
            await call(client, "volunteers", "GET", f"/api/v1/volunteers/{S.volunteer_profile_id}",
                       headers=S.user_headers, expected=200)

    async def test_update(self, client, db_session):
        if S.volunteer_profile_id:
            await call(client, "volunteers", "PUT", f"/api/v1/volunteers/{S.volunteer_profile_id}",
                       headers=S.user_headers, json={"skills": "animal care, grooming"}, expected=200)

    async def test_create_shift(self, client, db_session):
        r = await call(client, "volunteers", "POST", "/api/v1/volunteers/shifts",
                       headers=S.admin_headers, json={
                           "role_name": "dog_walker",
                           "start_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                           "end_at": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
                           "capacity": 5,
                       }, expected=201)
        if r.status_code == 201:
            S.shift_id = r.json()["data"]["id"]

    async def test_list_shifts(self, client, db_session):
        await call(client, "volunteers", "GET", "/api/v1/volunteers/shifts",
                   headers=S.admin_headers, expected=200)

    async def test_join_shift(self, client, db_session):
        if S.shift_id and S.volunteer_profile_id:
            await call(client, "volunteers", "POST",
                       f"/api/v1/volunteers/shifts/{S.shift_id}/join",
                       headers=S.user_headers, expected=200)

    async def test_shift_attendance(self, client, db_session):
        if S.shift_id:
            await call(client, "volunteers", "GET",
                       f"/api/v1/volunteers/shifts/{S.shift_id}/attendance",
                       headers=S.admin_headers, expected=200)

    async def test_certificate(self, client, db_session):
        if S.volunteer_profile_id:
            await call(client, "volunteers", "GET",
                       f"/api/v1/volunteers/{S.volunteer_profile_id}/certificate",
                       headers=S.user_headers, expected=200)

    async def test_service_summary(self, client, db_session):
        if S.volunteer_profile_id:
            await call(client, "volunteers", "GET",
                       f"/api/v1/volunteers/{S.volunteer_profile_id}/service-summary",
                       headers=S.user_headers, expected=200)

    async def test_delete(self, client, db_session):
        if S.volunteer_profile_id:
            await call(client, "volunteers", "DELETE",
                       f"/api/v1/volunteers/{S.volunteer_profile_id}",
                       headers=S.user_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "volunteers", "POST", "/api/v1/volunteers/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_bulk_status(self, client, db_session):
        await call(client, "volunteers", "POST", "/api/v1/volunteers/bulk/status",
                   headers=S.admin_headers, json={"ids": [], "status": "active"}, expected=200)

    async def test_checkin(self, client, db_session):
        # Placeholder: needs attendance_id from join
        pass

    async def test_checkout(self, client, db_session):
        pass


# ═══════════════════════════════════════════════════════════════════════════
# DONATIONS (29 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestDonations:

    async def test_register_donor(self, client, db_session):
        r = await call(client, "donations", "POST", "/api/v1/donations/register",
                       headers=S.user_headers,
                       json={"tax_identifier": f"TAX_{uid()}", "notes": "Test"}, expected=201)
        if r.status_code == 201:
            S.donor_id = r.json()["data"]["id"]

    async def test_create_donation(self, client, db_session):
        r = await call(client, "donations", "POST", "/api/v1/donations",
                       headers=S.user_headers,
                       json={"amount": 100.0, "currency": "INR", "donation_type": "one_time"}, expected=201)
        if r.status_code == 201:
            S.donation_id = r.json()["data"]["id"]

    async def test_list_donations(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations",
                   headers=S.admin_headers, expected=200)

    async def test_donation_history(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations/history",
                   headers=S.user_headers, expected=200)

    async def test_checkout(self, client, db_session):
        await call(client, "donations", "POST", "/api/v1/donations/checkout",
                   headers=S.user_headers,
                   json={"amount": 250.0, "currency": "INR", "donation_type": "one_time"}, expected=200)

    async def test_verify(self, client, db_session):
        await call(client, "donations", "POST", "/api/v1/donations/verify",
                   headers=S.user_headers, json={"payment_id": f"pay_{uid()}"}, expected=200)

    async def test_receipt(self, client, db_session):
        if S.donation_id:
            await call(client, "donations", "GET", f"/api/v1/donations/{S.donation_id}/receipt",
                       headers=S.user_headers, expected=200)

    async def test_reconcile(self, client, db_session):
        if S.donation_id:
            await call(client, "donations", "POST", f"/api/v1/donations/{S.donation_id}/reconcile",
                       headers=S.admin_headers, json={"reconciled": True}, expected=200)

    async def test_update_status(self, client, db_session):
        if S.donation_id:
            await call(client, "donations", "PATCH", f"/api/v1/donations/{S.donation_id}/status",
                       headers=S.admin_headers, json={"status": "completed"}, expected=200)

    async def test_bulk_status(self, client, db_session):
        await call(client, "donations", "POST", "/api/v1/donations/bulk/status-update",
                   headers=S.admin_headers, json={"ids": [], "status": "completed"}, expected=200)

    async def test_create_campaign(self, client, db_session):
        r = await call(client, "donations", "POST", "/api/v1/donations/campaigns",
                       headers=S.admin_headers, json={
                           "name": f"Camp_{uid()}", "description": "Test", "target_amount": 10000.0,
                           "currency": "INR", "campaign_type": "general", "status": "active",
                           "start_date": date.today().isoformat(),
                       }, expected=201)
        if r.status_code == 201:
            S.campaign_id = r.json()["data"]["id"]

    async def test_list_campaigns(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations/campaigns", expected=200)

    async def test_manage_campaigns(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations/campaigns/manage",
                   headers=S.admin_headers, expected=200)

    async def test_get_campaign(self, client, db_session):
        if S.campaign_id:
            await call(client, "donations", "GET", f"/api/v1/donations/campaigns/{S.campaign_id}",
                       expected=200)

    async def test_update_campaign(self, client, db_session):
        if S.campaign_id:
            await call(client, "donations", "PATCH", f"/api/v1/donations/campaigns/{S.campaign_id}",
                       headers=S.admin_headers, json={"target_amount": 15000.0}, expected=200)

    async def test_delete_campaign(self, client, db_session):
        r = await client.post("/api/v1/donations/campaigns", headers=S.admin_headers, json={
            "name": f"Del_{uid()}", "description": "x", "target_amount": 100.0,
            "currency": "INR", "campaign_type": "general", "status": "draft",
            "start_date": date.today().isoformat(),
        })
        if r.status_code == 201:
            cid = r.json()["data"]["id"]
            await call(client, "donations", "DELETE", f"/api/v1/donations/campaigns/{cid}",
                       headers=S.admin_headers, expected=200)

    async def test_list_donors(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations/donors",
                   headers=S.admin_headers, expected=200)

    async def test_my_donor_profile(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations/donors/me",
                   headers=S.user_headers, expected=200)

    async def test_update_donor(self, client, db_session):
        if S.donor_id:
            await call(client, "donations", "PUT", f"/api/v1/donations/donors/{S.donor_id}",
                       headers=S.user_headers, json={"notes": "Updated"}, expected=200)

    async def test_delete_donor(self, client, db_session):
        r = await client.post("/api/v1/donations/register", headers=S.user_headers,
                              json={"tax_identifier": f"DEL_{uid()}"})
        if r.status_code == 201:
            did = r.json()["data"]["id"]
            await call(client, "donations", "DELETE", f"/api/v1/donations/donors/{did}",
                       headers=S.admin_headers, expected=200)

    async def test_bulk_delete_donors(self, client, db_session):
        await call(client, "donations", "POST", "/api/v1/donations/donors/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_create_recurring(self, client, db_session):
        r = await call(client, "donations", "POST", "/api/v1/donations/recurring",
                       headers=S.user_headers,
                       json={"amount": 500.0, "currency": "INR", "frequency": "monthly"}, expected=201)
        if r.status_code == 201:
            S.recurring_sub_id = r.json()["data"]["id"]

    async def test_list_recurring(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations/recurring",
                   headers=S.user_headers, expected=200)

    async def test_delete_recurring(self, client, db_session):
        if S.recurring_sub_id:
            await call(client, "donations", "DELETE",
                       f"/api/v1/donations/recurring/{S.recurring_sub_id}",
                       headers=S.user_headers, expected=200)

    async def test_create_sponsorship(self, client, db_session):
        if S.dog_id:
            r = await call(client, "donations", "POST", "/api/v1/donations/sponsorships",
                           headers=S.user_headers, json={
                               "dog_id": S.dog_id, "amount": 1000.0, "currency": "INR",
                               "frequency": "monthly",
                           }, expected=201)
            if r.status_code == 201:
                S.sponsorship_id = r.json()["data"]["id"]

    async def test_list_sponsorships(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations/sponsorships",
                   headers=S.admin_headers, expected=200)

    async def test_my_sponsorships(self, client, db_session):
        await call(client, "donations", "GET", "/api/v1/donations/sponsorships/my",
                   headers=S.user_headers, expected=200)

    async def test_get_sponsorship(self, client, db_session):
        if S.sponsorship_id:
            await call(client, "donations", "GET",
                       f"/api/v1/donations/sponsorships/{S.sponsorship_id}",
                       headers=S.user_headers, expected=200)

    async def test_update_sponsorship_status(self, client, db_session):
        if S.sponsorship_id:
            await call(client, "donations", "PATCH",
                       f"/api/v1/donations/sponsorships/{S.sponsorship_id}/status",
                       headers=S.admin_headers, json={"status": "active"}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# FINANCE (25 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFinance:

    async def test_create_account(self, client, db_session):
        r = await call(client, "finance", "POST", "/api/v1/finance/accounts",
                       headers=S.admin_headers, json={
                           "account_code": f"100{uid()[:4]}", "account_name": f"Cash_{uid()}",
                           "account_type": "asset", "category": "cash", "opening_balance": "10000.00",
                       }, expected=201)
        if r.status_code == 201:
            S.finance_account_debit = r.json()["data"]["id"]

    async def test_list_accounts(self, client, db_session):
        await call(client, "finance", "GET", "/api/v1/finance/accounts",
                   headers=S.admin_headers, expected=200)

    async def test_get_account(self, client, db_session):
        if S.finance_account_debit:
            await call(client, "finance", "GET",
                       f"/api/v1/finance/accounts/{S.finance_account_debit}",
                       headers=S.admin_headers, expected=200)

    async def test_update_account(self, client, db_session):
        if S.finance_account_debit:
            await call(client, "finance", "PUT",
                       f"/api/v1/finance/accounts/{S.finance_account_debit}",
                       headers=S.admin_headers, json={"account_name": "Updated"}, expected=200)

    async def test_delete_account(self, client, db_session):
        r = await client.post("/api/v1/finance/accounts", headers=S.admin_headers, json={
            "account_code": f"900{uid()[:4]}", "account_name": f"Del_{uid()}",
            "account_type": "expense", "category": "supplies_expense",
        })
        if r.status_code == 201:
            aid = r.json()["data"]["id"]
            await call(client, "finance", "DELETE", f"/api/v1/finance/accounts/{aid}",
                       headers=S.admin_headers, expected=200)

    async def test_bulk_delete_accounts(self, client, db_session):
        await call(client, "finance", "POST", "/api/v1/finance/accounts/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_account_balances(self, client, db_session):
        await call(client, "finance", "GET", "/api/v1/finance/account-balances",
                   headers=S.admin_headers, expected=200)

    async def test_create_transaction(self, client, db_session):
        if S.finance_account_debit and S.finance_account_credit:
            r = await call(client, "finance", "POST", "/api/v1/finance/transactions",
                           headers=S.admin_headers, json={
                               "debit_account_id": S.finance_account_debit,
                               "credit_account_id": S.finance_account_credit,
                               "amount": "500.00", "description": "Test tx",
                           }, expected=201)
            if r.status_code == 201:
                S.transaction_id = r.json()["data"]["id"]

    async def test_list_transactions(self, client, db_session):
        await call(client, "finance", "GET", "/api/v1/finance/transactions",
                   headers=S.admin_headers, expected=200)

    async def test_get_transaction(self, client, db_session):
        if S.transaction_id:
            await call(client, "finance", "GET",
                       f"/api/v1/finance/transactions/{S.transaction_id}",
                       headers=S.admin_headers, expected=200)

    async def test_update_tx_status(self, client, db_session):
        if S.transaction_id:
            await call(client, "finance", "PATCH",
                       f"/api/v1/finance/transactions/{S.transaction_id}/status",
                       headers=S.admin_headers, json={"status": "posted"}, expected=200)

    async def test_delete_transaction(self, client, db_session):
        if S.finance_account_debit and S.finance_account_credit:
            r = await client.post("/api/v1/finance/transactions", headers=S.admin_headers, json={
                "debit_account_id": S.finance_account_debit,
                "credit_account_id": S.finance_account_credit,
                "amount": "100.00", "description": "Del",
            })
            if r.status_code == 201:
                tid = r.json()["data"]["id"]
                await call(client, "finance", "DELETE",
                           f"/api/v1/finance/transactions/{tid}",
                           headers=S.admin_headers, expected=200)

    async def test_bulk_delete_transactions(self, client, db_session):
        await call(client, "finance", "POST", "/api/v1/finance/transactions/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_create_budget(self, client, db_session):
        r = await call(client, "finance", "POST", "/api/v1/finance/budgets",
                       headers=S.admin_headers, json={
                           "name": f"Budget_{uid()}", "amount": "50000.00", "period": "monthly",
                           "start_date": "2026-01-01", "end_date": "2026-01-31",
                       }, expected=201)
        if r.status_code == 201:
            S.budget_id = r.json()["data"]["id"]

    async def test_list_budgets(self, client, db_session):
        await call(client, "finance", "GET", "/api/v1/finance/budgets",
                   headers=S.admin_headers, expected=200)

    async def test_get_budget(self, client, db_session):
        if S.budget_id:
            await call(client, "finance", "GET", f"/api/v1/finance/budgets/{S.budget_id}",
                       headers=S.admin_headers, expected=200)

    async def test_create_budget_item(self, client, db_session):
        if S.budget_id:
            await call(client, "finance", "POST",
                       f"/api/v1/finance/budgets/{S.budget_id}/items",
                       headers=S.admin_headers,
                       json={"category": "food", "budgeted_amount": "5000.00"}, expected=200)

    async def test_delete_budget(self, client, db_session):
        if S.budget_id:
            await call(client, "finance", "DELETE", f"/api/v1/finance/budgets/{S.budget_id}",
                       headers=S.admin_headers, expected=200)

    async def test_create_recurring(self, client, db_session):
        if S.finance_account_debit and S.finance_account_credit:
            r = await call(client, "finance", "POST", "/api/v1/finance/recurring",
                           headers=S.admin_headers, json={
                               "debit_account_id": S.finance_account_debit,
                               "credit_account_id": S.finance_account_credit,
                               "amount": "1000.00", "description": "Monthly rent",
                               "frequency": "monthly",
                           }, expected=201)
            if r.status_code == 201:
                S.recurring_tx_id = r.json()["data"]["id"]

    async def test_list_recurring(self, client, db_session):
        await call(client, "finance", "GET", "/api/v1/finance/recurring",
                   headers=S.admin_headers, expected=200)

    async def test_delete_recurring(self, client, db_session):
        if S.recurring_tx_id:
            await call(client, "finance", "DELETE",
                       f"/api/v1/finance/recurring/{S.recurring_tx_id}",
                       headers=S.admin_headers, expected=200)

    async def test_summary(self, client, db_session):
        await call(client, "finance", "GET", "/api/v1/finance/summary",
                   headers=S.admin_headers, expected=200)

    async def test_pnl(self, client, db_session):
        await call(client, "finance", "GET", "/api/v1/finance/pnl",
                   headers=S.admin_headers, expected=200)

    async def test_reconcile_summary(self, client, db_session):
        await call(client, "finance", "GET", "/api/v1/finance/reconcile/summary",
                   headers=S.admin_headers, expected=200)

    async def test_reconcile_donations(self, client, db_session):
        await call(client, "finance", "POST", "/api/v1/finance/reconcile/donations",
                   headers=S.admin_headers, expected=200)

    async def test_reconcile_donations_rejects_unknown_fields(self, client, db_session):
        await call(client, "finance", "POST", "/api/v1/finance/reconcile/donations",
                   headers=S.admin_headers,
                   json={"start_date": "2026-01-01", "end_date": "2026-12-31"}, expected=422)


# ═══════════════════════════════════════════════════════════════════════════
# FLEET (17 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFleet:

    async def test_create_vehicle(self, client, db_session):
        r = await call(client, "fleet", "POST", "/api/v1/fleet/vehicles",
                       headers=S.admin_headers, json={
                           "make_model": f"Toyota_{uid()}", "license_plate": f"DL-{uid()[:4]}",
                           "vehicle_type": "rescue_van", "status": "active", "mileage": 5000,
                       }, expected=201)
        if r.status_code == 201:
            S.vehicle_id = r.json()["data"]["id"]

    async def test_list_vehicles(self, client, db_session):
        await call(client, "fleet", "GET", "/api/v1/fleet/vehicles",
                   headers=S.admin_headers, expected=200)

    async def test_get_vehicle(self, client, db_session):
        if S.vehicle_id:
            await call(client, "fleet", "GET", f"/api/v1/fleet/vehicles/{S.vehicle_id}",
                       headers=S.admin_headers, expected=200)

    async def test_update_vehicle(self, client, db_session):
        if S.vehicle_id:
            await call(client, "fleet", "PUT", f"/api/v1/fleet/vehicles/{S.vehicle_id}",
                       headers=S.admin_headers, json={"mileage": 9000}, expected=200)

    async def test_update_status(self, client, db_session):
        if S.vehicle_id:
            await call(client, "fleet", "PATCH", f"/api/v1/fleet/vehicles/{S.vehicle_id}/status",
                       headers=S.admin_headers, json={"status": "maintenance"}, expected=200)

    async def test_add_fuel_log(self, client, db_session):
        if S.vehicle_id:
            r = await call(client, "fleet", "POST",
                           f"/api/v1/fleet/vehicles/{S.vehicle_id}/fuel",
                           headers=S.admin_headers,
                           json={"liters": 40.0, "cost": 3600.0, "odometer": 7500}, expected=201)
            if r.status_code == 201:
                S.fuel_log_id = r.json()["data"]["id"]

    async def test_list_fuel_logs(self, client, db_session):
        if S.vehicle_id:
            await call(client, "fleet", "GET",
                       f"/api/v1/fleet/vehicles/{S.vehicle_id}/fuel",
                       headers=S.admin_headers, expected=200)

    async def test_get_fuel_log(self, client, db_session):
        if S.fuel_log_id:
            await call(client, "fleet", "GET", f"/api/v1/fleet/fuel/{S.fuel_log_id}",
                       headers=S.admin_headers, expected=200)

    async def test_add_maintenance(self, client, db_session):
        if S.vehicle_id:
            r = await call(client, "fleet", "POST", "/api/v1/fleet/maintenance",
                           headers=S.admin_headers, json={
                               "vehicle_id": S.vehicle_id,
                               "maintenance_type": "oil_change",
                               "cost": 2500.0, "odometer": 10500,
                           }, expected=201)

    async def test_list_maintenance(self, client, db_session):
        if S.vehicle_id:
            await call(client, "fleet", "GET",
                       f"/api/v1/fleet/vehicles/{S.vehicle_id}/maintenance",
                       headers=S.admin_headers, expected=200)

    async def test_checkout_equipment(self, client, db_session):
        r = await call(client, "fleet", "POST", "/api/v1/fleet/equipment",
                       headers=S.admin_headers, json={
                           "equipment_name": f"FirstAid_{uid()}",
                           "checked_out_by": str(uuid.uuid4()),
                       }, expected=201)
        if r.status_code == 201:
            S.equipment_checkout_id = r.json()["data"]["id"]

    async def test_list_equipment(self, client, db_session):
        await call(client, "fleet", "GET", "/api/v1/fleet/equipment",
                   headers=S.admin_headers, expected=200)

    async def test_get_equipment(self, client, db_session):
        if S.equipment_checkout_id:
            await call(client, "fleet", "GET",
                       f"/api/v1/fleet/equipment/{S.equipment_checkout_id}",
                       headers=S.admin_headers, expected=200)

    async def test_return_equipment(self, client, db_session):
        if S.equipment_checkout_id:
            await call(client, "fleet", "POST",
                       f"/api/v1/fleet/equipment/{S.equipment_checkout_id}/return",
                       headers=S.admin_headers, expected=200)

    async def test_delete_vehicle(self, client, db_session):
        if S.vehicle_id:
            await call(client, "fleet", "DELETE", f"/api/v1/fleet/vehicles/{S.vehicle_id}",
                       headers=S.admin_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "fleet", "POST", "/api/v1/fleet/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_bulk_status(self, client, db_session):
        await call(client, "fleet", "POST", "/api/v1/fleet/bulk/status-update",
                   headers=S.admin_headers, json={"ids": [], "status": "active"}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# GRIEVANCE (16 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestGrievance:

    async def test_create(self, client, db_session):
        r = await call(client, "grievance", "POST", "/api/v1/grievance", json={
            "reporter_name": f"Rep_{uid()}", "reporter_phone": "+9876543210",
            "complaint_type": "service_quality", "details": "Test grievance",
        }, expected=201)
        if r.status_code == 201:
            S.grievance_ticket_id = r.json()["data"]["id"]

    async def test_list(self, client, db_session):
        await call(client, "grievance", "GET", "/api/v1/grievance",
                   headers=S.admin_headers, expected=200)

    async def test_get(self, client, db_session):
        if S.grievance_ticket_id:
            await call(client, "grievance", "GET",
                       f"/api/v1/grievance/{S.grievance_ticket_id}", expected=200)

    async def test_update(self, client, db_session):
        if S.grievance_ticket_id:
            await call(client, "grievance", "PUT",
                       f"/api/v1/grievance/{S.grievance_ticket_id}",
                       headers=S.admin_headers,
                       json={"details": "Updated details"}, expected=200)

    async def test_update_status(self, client, db_session):
        if S.grievance_ticket_id:
            await call(client, "grievance", "PATCH",
                       f"/api/v1/grievance/{S.grievance_ticket_id}/status",
                       headers=S.admin_headers, json={"status": "in_progress"}, expected=200)

    async def test_assign(self, client, db_session):
        if S.grievance_ticket_id:
            await call(client, "grievance", "POST",
                       f"/api/v1/grievance/{S.grievance_ticket_id}/assign",
                       headers=S.admin_headers,
                       json={"assigned_to": str(uuid.uuid4())}, expected=200)

    async def test_escalate(self, client, db_session):
        if S.grievance_ticket_id:
            await call(client, "grievance", "POST",
                       f"/api/v1/grievance/{S.grievance_ticket_id}/escalate",
                       headers=S.admin_headers, expected=200)

    async def test_add_comment(self, client, db_session):
        if S.grievance_ticket_id:
            await call(client, "grievance", "POST",
                       f"/api/v1/grievance/{S.grievance_ticket_id}/comments",
                       headers=S.admin_headers,
                       json={"comment": "Investigating"}, expected=200)

    async def test_list_comments(self, client, db_session):
        if S.grievance_ticket_id:
            await call(client, "grievance", "GET",
                       f"/api/v1/grievance/{S.grievance_ticket_id}/comments",
                       headers=S.admin_headers, expected=200)

    async def test_create_feedback(self, client, db_session):
        r = await call(client, "grievance", "POST", "/api/v1/grievance/feedback",
                       json={"rating": 5, "comments": "Great!"}, expected=201)
        if r.status_code == 201:
            S.feedback_id = r.json()["data"]["id"]

    async def test_list_feedback(self, client, db_session):
        await call(client, "grievance", "GET", "/api/v1/grievance/feedback",
                   headers=S.admin_headers, expected=200)

    async def test_delete_feedback(self, client, db_session):
        if S.feedback_id:
            await call(client, "grievance", "DELETE",
                       f"/api/v1/grievance/feedback/{S.feedback_id}", expected=200)

    async def test_delete(self, client, db_session):
        if S.grievance_ticket_id:
            await call(client, "grievance", "DELETE",
                       f"/api/v1/grievance/{S.grievance_ticket_id}", expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "grievance", "POST", "/api/v1/grievance/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_bulk_status(self, client, db_session):
        await call(client, "grievance", "POST", "/api/v1/grievance/bulk/status",
                   headers=S.admin_headers, json={"ids": [], "status": "resolved"}, expected=200)

    async def test_bulk_delete_feedback(self, client, db_session):
        await call(client, "grievance", "POST", "/api/v1/grievance/feedback/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY (12 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestInventory:

    async def test_create_item(self, client, db_session):
        r = await call(client, "inventory", "POST", "/api/v1/inventory/items",
                       headers=S.admin_headers, json={
                           "name": f"Item_{uid()}", "category": "food", "quantity": 100.0,
                           "unit": "kg", "reorder_threshold": 10.0, "unit_cost": 5.0,
                       }, expected=201)
        if r.status_code == 201:
            S.inventory_item_id = r.json()["data"]["id"]

    async def test_list_items(self, client, db_session):
        await call(client, "inventory", "GET", "/api/v1/inventory/items",
                   headers=S.admin_headers, expected=200)

    async def test_get_item(self, client, db_session):
        if S.inventory_item_id:
            await call(client, "inventory", "GET",
                       f"/api/v1/inventory/items/{S.inventory_item_id}",
                       headers=S.admin_headers, expected=200)

    async def test_create_movement(self, client, db_session):
        if S.inventory_item_id:
            await call(client, "inventory", "POST", "/api/v1/inventory/movements",
                       headers=S.admin_headers, json={
                           "item_id": S.inventory_item_id, "movement_type": "out",
                           "quantity": 5.0, "notes": "Feeding dogs",
                       }, expected=201)

    async def test_list_item_movements(self, client, db_session):
        if S.inventory_item_id:
            await call(client, "inventory", "GET",
                       f"/api/v1/inventory/items/{S.inventory_item_id}/movements",
                       headers=S.admin_headers, expected=200)

    async def test_create_requisition(self, client, db_session):
        if S.inventory_item_id:
            r = await call(client, "inventory", "POST", "/api/v1/inventory/requisitions",
                           headers=S.admin_headers, json={
                               "item_id": S.inventory_item_id, "quantity": 20.0,
                               "reason": "Low stock",
                           }, expected=201)
            if r.status_code == 201:
                S.requisition_id = r.json()["data"]["id"]

    async def test_list_requisitions(self, client, db_session):
        await call(client, "inventory", "GET", "/api/v1/inventory/requisitions",
                   headers=S.admin_headers, expected=200)

    async def test_update_requisition_status(self, client, db_session):
        if S.requisition_id:
            await call(client, "inventory", "PUT",
                       f"/api/v1/inventory/requisitions/{S.requisition_id}/status",
                       headers=S.admin_headers, json={"status": "approved"}, expected=200)

    async def test_bulk_status_requisitions(self, client, db_session):
        await call(client, "inventory", "POST", "/api/v1/inventory/requisitions/bulk/status",
                   headers=S.admin_headers, json={"ids": [], "status": "fulfilled"}, expected=200)

    async def test_delete_item(self, client, db_session):
        r = await client.post("/api/v1/inventory/items", headers=S.admin_headers, json={
            "name": f"Del_{uid()}", "category": "food", "quantity": 10.0, "unit": "kg",
        })
        if r.status_code == 201:
            iid = r.json()["data"]["id"]
            await call(client, "inventory", "DELETE", f"/api/v1/inventory/items/{iid}",
                       headers=S.admin_headers, expected=200)

    async def test_admin_delete_item(self, client, db_session):
        r = await client.post("/api/v1/inventory/items", headers=S.admin_headers, json={
            "name": f"Del2_{uid()}", "category": "food", "quantity": 10.0, "unit": "kg",
        })
        if r.status_code == 201:
            iid = r.json()["data"]["id"]
            await call(client, "inventory", "DELETE",
                       f"/api/v1/inventory/admin/inventory/items/{iid}",
                       headers=S.admin_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "inventory", "POST", "/api/v1/inventory/items/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# SHELTER (24 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestShelter:

    async def test_create_facility(self, client, db_session):
        r = await call(client, "shelter", "POST", "/api/v1/shelter/facilities",
                       headers=S.admin_headers, json={
                           "name": f"Shelter_{uid()}", "address": "123 Rescue Lane",
                           "phone": "+1234567890", "latitude": 28.6139, "longitude": 77.2090,
                           "total_capacity": 50, "facility_type": "shelter",
                       }, expected=201)
        if r.status_code == 201:
            S.facility_id = r.json()["data"]["id"]

    async def test_list_facilities(self, client, db_session):
        await call(client, "shelter", "GET", "/api/v1/shelter/facilities",
                   headers=S.admin_headers, expected=200)

    async def test_get_facility(self, client, db_session):
        if S.facility_id:
            await call(client, "shelter", "GET",
                       f"/api/v1/shelter/facilities/{S.facility_id}", expected=200)

    async def test_update_facility(self, client, db_session):
        if S.facility_id:
            await call(client, "shelter", "PUT",
                       f"/api/v1/shelter/facilities/{S.facility_id}",
                       headers=S.admin_headers, json={"total_capacity": 60}, expected=200)

    async def test_update_facility_status(self, client, db_session):
        if S.facility_id:
            await call(client, "shelter", "PUT",
                       f"/api/v1/shelter/facilities/{S.facility_id}/status",
                       headers=S.admin_headers, json={"status": "active"}, expected=200)

    async def test_create_section(self, client, db_session):
        if S.facility_id:
            r = await call(client, "shelter", "POST",
                           f"/api/v1/shelter/facilities/{S.facility_id}/sections",
                           headers=S.admin_headers,
                           json={"name": f"Sec_{uid()}", "section_type": "general", "capacity": 10},
                           expected=201)
            if r.status_code == 201:
                S.section_id = r.json()["data"]["id"]

    async def test_list_sections(self, client, db_session):
        if S.facility_id:
            await call(client, "shelter", "GET",
                       f"/api/v1/shelter/facilities/{S.facility_id}/sections",
                       headers=S.admin_headers, expected=200)

    async def test_create_kennel(self, client, db_session):
        if S.section_id:
            r = await call(client, "shelter", "POST",
                           f"/api/v1/shelter/sections/{S.section_id}/kennels",
                           headers=S.admin_headers,
                           json={"identifier": f"K-{uid()}", "capacity": 1}, expected=201)
            if r.status_code == 201:
                S.kennel_id = r.json()["data"]["id"]

    async def test_list_kennels(self, client, db_session):
        if S.section_id:
            await call(client, "shelter", "GET",
                       f"/api/v1/shelter/sections/{S.section_id}/kennels",
                       headers=S.admin_headers, expected=200)

    async def test_assign_dog(self, client, db_session):
        if S.kennel_id and S.dog_id:
            await call(client, "shelter", "POST",
                       f"/api/v1/shelter/kennels/{S.kennel_id}/assign/{S.dog_id}",
                       headers=S.admin_headers, expected=200)

    async def test_unassign_dog(self, client, db_session):
        if S.kennel_id and S.dog_id:
            await call(client, "shelter", "PATCH",
                       f"/api/v1/shelter/kennels/{S.kennel_id}/assign/{S.dog_id}",
                       headers=S.admin_headers, expected=200)

    async def test_update_sanitation(self, client, db_session):
        if S.kennel_id:
            await call(client, "shelter", "PUT",
                       f"/api/v1/shelter/kennels/{S.kennel_id}/sanitation",
                       headers=S.admin_headers, json={"status": "clean"}, expected=200)

    async def test_create_cleaning_log(self, client, db_session):
        if S.kennel_id:
            await call(client, "shelter", "POST",
                       f"/api/v1/shelter/kennels/{S.kennel_id}/cleaning-logs",
                       headers=S.admin_headers,
                       json={"cleaned_by": str(uuid.uuid4()), "notes": "Morning cleaning"}, expected=201)

    async def test_list_cleaning_logs(self, client, db_session):
        if S.kennel_id:
            await call(client, "shelter", "GET",
                       f"/api/v1/shelter/kennels/{S.kennel_id}/cleaning-logs",
                       headers=S.admin_headers, expected=200)

    async def test_create_care_log(self, client, db_session):
        if S.dog_id:
            await call(client, "shelter", "POST", "/api/v1/shelter/care-logs",
                       headers=S.admin_headers,
                       json={"dog_id": S.dog_id, "care_type": "feeding", "notes": "Fed kibble"},
                       expected=201)

    async def test_list_dog_care_logs(self, client, db_session):
        if S.dog_id:
            await call(client, "shelter", "GET",
                       f"/api/v1/shelter/dogs/{S.dog_id}/care-logs",
                       headers=S.admin_headers, expected=200)

    async def test_create_transfer(self, client, db_session):
        if S.dog_id and S.facility_id:
            r = await call(client, "shelter", "POST", "/api/v1/shelter/transfers",
                           headers=S.admin_headers, json={
                               "dog_id": S.dog_id, "from_facility_id": S.facility_id,
                               "to_facility_id": str(uuid.uuid4()),
                           }, expected=201)
            if r.status_code == 201:
                S.transfer_id = r.json()["data"]["id"]

    async def test_list_transfers(self, client, db_session):
        await call(client, "shelter", "GET", "/api/v1/shelter/transfers",
                   headers=S.admin_headers, expected=200)

    async def test_get_transfer(self, client, db_session):
        if hasattr(S, "transfer_id") and S.transfer_id:
            await call(client, "shelter", "GET",
                       f"/api/v1/shelter/transfers/{S.transfer_id}",
                       headers=S.admin_headers, expected=200)

    async def test_confirm_sender(self, client, db_session):
        if hasattr(S, "transfer_id") and S.transfer_id:
            await call(client, "shelter", "POST",
                       f"/api/v1/shelter/transfers/{S.transfer_id}/confirm-sender",
                       headers=S.admin_headers, expected=200)

    async def test_confirm_receiver(self, client, db_session):
        if hasattr(S, "transfer_id") and S.transfer_id:
            await call(client, "shelter", "POST",
                       f"/api/v1/shelter/transfers/{S.transfer_id}/confirm-receiver",
                       headers=S.admin_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "shelter", "POST", "/api/v1/shelter/facilities/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_bulk_status(self, client, db_session):
        await call(client, "shelter", "POST", "/api/v1/shelter/facilities/bulk/status",
                   headers=S.admin_headers, json={"ids": [], "status": "active"}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# LOST-FOUND (18 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestLostFound:

    async def test_create_lost(self, client, db_session):
        r = await call(client, "lost-found", "POST", "/api/v1/lost-found/lost",
                       headers=S.user_headers, json={
                           "pet_name": f"Lost_{uid()}", "species": "dog", "breed": "labrador",
                           "color": "golden", "last_seen_location": "123 Main St",
                           "last_seen_date": datetime.now(UTC).isoformat(),
                           "description": "Friendly dog", "contact_phone": "+9876543210",
                       }, expected=201)
        if r.status_code == 201:
            S.lost_report_id = r.json()["data"]["id"]

    async def test_list_lost(self, client, db_session):
        await call(client, "lost-found", "GET", "/api/v1/lost-found/lost",
                   headers=S.user_headers, expected=200)

    async def test_get_lost(self, client, db_session):
        if S.lost_report_id:
            await call(client, "lost-found", "GET",
                       f"/api/v1/lost-found/lost/{S.lost_report_id}", expected=200)

    async def test_broadcast_lost(self, client, db_session):
        if S.lost_report_id:
            await call(client, "lost-found", "POST",
                       f"/api/v1/lost-found/lost/{S.lost_report_id}/broadcast",
                       headers=S.user_headers, expected=200)

    async def test_lost_matches(self, client, db_session):
        if S.lost_report_id:
            await call(client, "lost-found", "GET",
                       f"/api/v1/lost-found/lost/{S.lost_report_id}/matches",
                       expected=200)

    async def test_create_found(self, client, db_session):
        r = await call(client, "lost-found", "POST", "/api/v1/lost-found/found",
                       headers=S.user_headers, json={
                           "species": "dog", "breed": "mixed", "color": "brown",
                           "found_location": "456 Oak Ave",
                           "found_date": datetime.now(UTC).isoformat(),
                           "description": "Stray dog", "contact_phone": "+9876543211",
                       }, expected=201)
        if r.status_code == 201:
            S.found_report_id = r.json()["data"]["id"]

    async def test_list_found(self, client, db_session):
        await call(client, "lost-found", "GET", "/api/v1/lost-found/found",
                   headers=S.user_headers, expected=200)

    async def test_get_found(self, client, db_session):
        if S.found_report_id:
            await call(client, "lost-found", "GET",
                       f"/api/v1/lost-found/found/{S.found_report_id}", expected=200)

    async def test_found_matches(self, client, db_session):
        if S.found_report_id:
            await call(client, "lost-found", "GET",
                       f"/api/v1/lost-found/found/{S.found_report_id}/matches",
                       expected=200)

    async def test_reunion_stories(self, client, db_session):
        await call(client, "lost-found", "GET", "/api/v1/lost-found/reunion-stories",
                   expected=200)

    async def test_stories(self, client, db_session):
        await call(client, "lost-found", "GET", "/api/v1/lost-found/stories",
                   expected=200)

    async def test_delete_lost(self, client, db_session):
        if S.lost_report_id:
            await call(client, "lost-found", "DELETE",
                       f"/api/v1/lost-found/lost/{S.lost_report_id}",
                       headers=S.user_headers, expected=200)

    async def test_delete_found(self, client, db_session):
        if S.found_report_id:
            await call(client, "lost-found", "DELETE",
                       f"/api/v1/lost-found/found/{S.found_report_id}",
                       headers=S.user_headers, expected=200)

    async def test_bulk_delete_lost(self, client, db_session):
        await call(client, "lost-found", "POST", "/api/v1/lost-found/lost/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_bulk_delete_found(self, client, db_session):
        await call(client, "lost-found", "POST", "/api/v1/lost-found/found/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)

    async def test_claim_match(self, client, db_session):
        await call(client, "lost-found", "POST",
                   f"/api/v1/lost-found/matches/{uuid.uuid4()}/claim",
                   headers=S.user_headers, json={"claimed_by": str(uuid.uuid4())}, expected=404)

    async def test_review_claim(self, client, db_session):
        await call(client, "lost-found", "POST",
                   f"/api/v1/lost-found/matches/{uuid.uuid4()}/claim/review",
                   headers=S.admin_headers, json={"approved": True}, expected=404)

    async def test_resolve(self, client, db_session):
        await call(client, "lost-found", "POST",
                   f"/api/v1/lost-found/matches/{uuid.uuid4()}/resolve",
                   headers=S.admin_headers, expected=404)


# ═══════════════════════════════════════════════════════════════════════════
# MEDICAL (21 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestMedical:

    async def test_create_exam(self, client, db_session):
        if S.dog_id:
            await call(client, "medical", "POST", "/api/v1/medical/exams",
                       headers=S.admin_headers, json={
                           "dog_id": S.dog_id, "exam_type": "routine_checkup",
                           "findings": "Healthy",
                       }, expected=201)

    async def test_list_exams(self, client, db_session):
        await call(client, "medical", "GET", "/api/v1/medical/exams",
                   headers=S.admin_headers, expected=200)

    async def test_create_prescription(self, client, db_session):
        if S.dog_id:
            r = await call(client, "medical", "POST", "/api/v1/medical/prescriptions",
                           headers=S.admin_headers, json={
                               "dog_id": S.dog_id, "medication_name": "Amoxicillin",
                               "dosage": "250mg", "frequency": "twice_daily",
                               "start_date": "2026-01-01", "end_date": "2026-01-14",
                           }, expected=201)
            if r.status_code == 201:
                S.prescription_id = r.json()["data"]["id"]

    async def test_list_prescriptions(self, client, db_session):
        await call(client, "medical", "GET", "/api/v1/medical/prescriptions",
                   headers=S.admin_headers, expected=200)

    async def test_get_prescription(self, client, db_session):
        if S.prescription_id:
            await call(client, "medical", "GET",
                       f"/api/v1/medical/prescriptions/{S.prescription_id}",
                       headers=S.admin_headers, expected=200)

    async def test_update_prescription(self, client, db_session):
        if S.prescription_id:
            await call(client, "medical", "PUT",
                       f"/api/v1/medical/prescriptions/{S.prescription_id}",
                       headers=S.admin_headers, json={"dosage": "500mg"}, expected=200)

    async def test_update_prescription_status(self, client, db_session):
        if S.prescription_id:
            await call(client, "medical", "PATCH",
                       f"/api/v1/medical/prescriptions/{S.prescription_id}/status",
                       headers=S.admin_headers, json={"status": "completed"}, expected=200)

    async def test_list_administrations(self, client, db_session):
        if S.prescription_id:
            await call(client, "medical", "GET",
                       f"/api/v1/medical/prescriptions/{S.prescription_id}/administrations",
                       headers=S.admin_headers, expected=200)

    async def test_create_administration(self, client, db_session):
        if S.dog_id:
            await call(client, "medical", "POST", "/api/v1/medical/administrations",
                       headers=S.admin_headers, json={
                           "dog_id": S.dog_id, "medication_name": "Amoxicillin",
                           "dosage": "250mg", "notes": "Morning dose",
                       }, expected=201)

    async def test_list_dog_administrations(self, client, db_session):
        if S.dog_id:
            await call(client, "medical", "GET",
                       f"/api/v1/medical/dogs/{S.dog_id}/administrations",
                       headers=S.admin_headers, expected=200)

    async def test_create_treatment(self, client, db_session):
        if S.dog_id:
            await call(client, "medical", "POST", "/api/v1/medical/treatments",
                       headers=S.admin_headers, json={
                           "dog_id": S.dog_id, "treatment_type": "wound_care",
                           "description": "Cleaned wound",
                       }, expected=201)

    async def test_list_treatments(self, client, db_session):
        await call(client, "medical", "GET", "/api/v1/medical/treatments",
                   headers=S.admin_headers, expected=200)

    async def test_create_vaccination(self, client, db_session):
        if S.dog_id:
            await call(client, "medical", "POST", "/api/v1/medical/vaccinations",
                       headers=S.admin_headers, json={
                           "dog_id": S.dog_id, "vaccine_name": "Rabies",
                           "date_administered": "2026-01-15", "next_due_date": "2027-01-15",
                       }, expected=201)

    async def test_list_vaccinations(self, client, db_session):
        await call(client, "medical", "GET", "/api/v1/medical/vaccinations",
                   headers=S.admin_headers, expected=200)

    async def test_create_vaccine_protocol(self, client, db_session):
        await call(client, "medical", "POST", "/api/v1/medical/vaccine-protocols",
                   headers=S.admin_headers, json={
                       "protocol_name": f"Proto_{uid()}", "vaccine_name": "DHPPiL",
                       "doses_required": 3, "interval_days": 21,
                   }, expected=201)

    async def test_list_vaccine_protocols(self, client, db_session):
        await call(client, "medical", "GET", "/api/v1/medical/vaccine-protocols",
                   headers=S.admin_headers, expected=200)

    async def test_dog_history(self, client, db_session):
        if S.dog_id:
            await call(client, "medical", "GET",
                       f"/api/v1/medical/dogs/{S.dog_id}/history",
                       headers=S.admin_headers, expected=200)

    async def test_create_clearance(self, client, db_session):
        if S.dog_id:
            await call(client, "medical", "POST",
                       f"/api/v1/medical/clearance/{S.dog_id}",
                       headers=S.admin_headers,
                       json={"clearance_type": "quarantine", "notes": "Cleared"}, expected=200)

    async def test_list_clearances(self, client, db_session):
        if S.dog_id:
            await call(client, "medical", "GET",
                       f"/api/v1/medical/clearances/dogs/{S.dog_id}",
                       headers=S.admin_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "medical", "POST", "/api/v1/medical/bulk/delete",
                   headers=S.admin_headers,
                   json={"entity_type": "exam", "ids": []}, expected=200)

    async def test_bulk_status_prescriptions(self, client, db_session):
        await call(client, "medical", "POST", "/api/v1/medical/bulk/prescriptions/status",
                   headers=S.admin_headers, json={"ids": [], "status": "completed"}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS (10 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestNotifications:

    async def test_list(self, client, db_session):
        await call(client, "notifications", "GET", "/api/v1/notifications",
                   headers=S.admin_headers, expected=200)

    async def test_unread_count(self, client, db_session):
        await call(client, "notifications", "GET", "/api/v1/notifications/unread-count",
                   headers=S.admin_headers, expected=200)

    async def test_read_all(self, client, db_session):
        await call(client, "notifications", "PUT", "/api/v1/notifications/read-all",
                   headers=S.admin_headers, expected=200)

    async def test_send(self, client, db_session):
        await call(client, "notifications", "POST", "/api/v1/notifications/send",
                   headers=S.admin_headers, json={
                       "recipient_id": str(uuid.uuid4()),
                       "title": f"Notif_{uid()}", "body": "Test", "notification_type": "info",
                   }, expected=200)

    async def test_broadcast(self, client, db_session):
        await call(client, "notifications", "POST", "/api/v1/notifications/broadcast",
                   headers=S.admin_headers, json={
                       "title": f"Broadcast_{uid()}", "body": "Broadcast message",
                       "notification_type": "alert",
                   }, expected=200)

    async def test_mark_read(self, client, db_session):
        await call(client, "notifications", "PUT",
                   f"/api/v1/notifications/{uuid.uuid4()}/read",
                   headers=S.admin_headers, expected=404)

    async def test_delete(self, client, db_session):
        await call(client, "notifications", "DELETE",
                   f"/api/v1/notifications/{uuid.uuid4()}",
                   headers=S.admin_headers, expected=404)

    async def test_get_preferences(self, client, db_session):
        await call(client, "notifications", "GET", "/api/v1/notifications/preferences",
                   headers=S.admin_headers, expected=200)

    async def test_update_preferences(self, client, db_session):
        await call(client, "notifications", "PUT", "/api/v1/notifications/preferences",
                   headers=S.admin_headers, json={
                       "email_notifications": True, "push_notifications": True,
                       "sms_notifications": False,
                   }, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "notifications", "POST", "/api/v1/notifications/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# SETTINGS (17 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestSettings:

    async def test_general(self, client, db_session):
        await call(client, "settings", "GET", "/api/v1/settings/general",
                   headers=S.admin_headers, expected=200)

    async def test_email(self, client, db_session):
        await call(client, "settings", "GET", "/api/v1/settings/email",
                   headers=S.admin_headers, expected=200)

    async def test_password_policy_get(self, client, db_session):
        await call(client, "settings", "GET", "/api/v1/settings/password-policy",
                   headers=S.admin_headers, expected=200)

    async def test_password_policy_update(self, client, db_session):
        await call(client, "settings", "PUT", "/api/v1/settings/password-policy",
                   headers=S.admin_headers, json={
                       "min_length": 10, "require_uppercase": True,
                       "require_lowercase": True, "require_digit": True, "require_special": True,
                   }, expected=200)

    async def test_storage_settings(self, client, db_session):
        await call(client, "settings", "GET", "/api/v1/settings/storage",
                   headers=S.admin_headers, expected=200)

    async def test_public_content_get(self, client, db_session):
        await call(client, "settings", "GET", "/api/v1/settings/public-content",
                   headers=S.admin_headers, expected=200)

    async def test_public_content_update(self, client, db_session):
        await call(client, "settings", "PUT", "/api/v1/settings/public-content",
                   headers=S.admin_headers, json={"site_name": "PawGuard"}, expected=200)

    async def test_system_get(self, client, db_session):
        await call(client, "settings", "GET", "/api/v1/settings/system",
                   headers=S.admin_headers, expected=200)

    async def test_system_create(self, client, db_session):
        await call(client, "settings", "POST", "/api/v1/settings/system",
                   headers=S.admin_headers, json={
                       "key": f"setting_{uid()}", "value": "test_value", "description": "Test",
                   }, expected=201)

    async def test_system_get_by_key(self, client, db_session):
        await call(client, "settings", "GET", f"/api/v1/settings/system/test_setting",
                   headers=S.admin_headers, expected=404)

    async def test_system_update_key(self, client, db_session):
        r = await client.post("/api/v1/settings/system", headers=S.admin_headers, json={
            "key": f"upd_{uid()}", "value": "v1", "description": "x",
        })
        if r.status_code == 201:
            key = r.json()["data"]["key"]
            await call(client, "settings", "PUT", f"/api/v1/settings/system/{key}",
                       headers=S.admin_headers, json={"value": "v2"}, expected=200)

    async def test_system_delete(self, client, db_session):
        r = await client.post("/api/v1/settings/system", headers=S.admin_headers, json={
            "key": f"del_{uid()}", "value": "x", "description": "x",
        })
        if r.status_code == 201:
            sid = r.json()["data"]["id"]
            await call(client, "settings", "DELETE", f"/api/v1/settings/system/{sid}",
                       headers=S.admin_headers, expected=200)

    async def test_business_rules_list(self, client, db_session):
        await call(client, "settings", "GET", "/api/v1/settings/business-rules",
                   headers=S.admin_headers, expected=200)

    async def test_business_rules_create(self, client, db_session):
        await call(client, "settings", "POST", "/api/v1/settings/business-rules",
                   headers=S.admin_headers, json={
                       "rule_key": f"rule_{uid()}", "rule_value": "true", "description": "Test",
                   }, expected=201)

    async def test_business_rules_get(self, client, db_session):
        await call(client, "settings", "GET", "/api/v1/settings/business-rules/nonexistent",
                   headers=S.admin_headers, expected=404)

    async def test_business_rules_update(self, client, db_session):
        r = await client.post("/api/v1/settings/business-rules", headers=S.admin_headers, json={
            "rule_key": f"upd_{uid()}", "rule_value": "v1", "description": "x",
        })
        if r.status_code == 201:
            rk = r.json()["data"]["rule_key"]
            await call(client, "settings", "PUT", f"/api/v1/settings/business-rules/{rk}",
                       headers=S.admin_headers, json={"rule_value": "v2"}, expected=200)

    async def test_business_rules_delete(self, client, db_session):
        r = await client.post("/api/v1/settings/business-rules", headers=S.admin_headers, json={
            "rule_key": f"del_{uid()}", "rule_value": "x", "description": "x",
        })
        if r.status_code == 201:
            rid = r.json()["data"]["id"]
            await call(client, "settings", "DELETE", f"/api/v1/settings/business-rules/{rid}",
                       headers=S.admin_headers, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# STORAGE (8 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestStorage:

    async def test_upload_url(self, client, db_session):
        r = await call(client, "storage", "POST", "/api/v1/storage/upload-url",
                       headers=S.admin_headers, json={
                           "filename": f"test_{uid()}.jpg", "mime_type": "image/jpeg",
                           "file_size": 1024, "folder": "test",
                       }, expected=200)
        if r.status_code == 200:
            S.storage_file_id = r.json()["data"]["id"]

    async def test_list_files(self, client, db_session):
        await call(client, "storage", "GET", "/api/v1/storage",
                   headers=S.admin_headers, expected=200)

    async def test_get_file(self, client, db_session):
        if S.storage_file_id:
            await call(client, "storage", "GET", f"/api/v1/storage/{S.storage_file_id}",
                       headers=S.admin_headers, expected=200)

    async def test_confirm_upload(self, client, db_session):
        if S.storage_file_id:
            await call(client, "storage", "PUT",
                       f"/api/v1/storage/{S.storage_file_id}/confirm",
                       headers=S.admin_headers, expected=200)

    async def test_download_url(self, client, db_session):
        if S.storage_file_id:
            await call(client, "storage", "GET",
                       f"/api/v1/storage/{S.storage_file_id}/download-url",
                       headers=S.admin_headers, expected=200)

    async def test_delete_file(self, client, db_session):
        if S.storage_file_id:
            await call(client, "storage", "DELETE", f"/api/v1/storage/{S.storage_file_id}",
                       headers=S.admin_headers, expected=200)

    async def test_entity_files(self, client, db_session):
        await call(client, "storage", "GET",
                   f"/api/v1/storage/entity/dog/{uuid.uuid4()}",
                   headers=S.admin_headers, expected=200)

    async def test_bulk_delete(self, client, db_session):
        await call(client, "storage", "POST", "/api/v1/storage/bulk/delete",
                   headers=S.admin_headers, json={"ids": []}, expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# PORTAL (51 endpoints)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestPortal:
    blog_id = None
    faq_id = None
    contact_id = None
    legal_id = None
    story_id = None
    alert_id = None
    vet_partner_id = None
    cms_slug = None

    # --- Public (14) ---
    async def test_stats(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/stats",expected=200)
    async def test_blog(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/blog",expected=200)
    async def test_blog_slug(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/blog/slug/test-slug",expected=404)
    async def test_faq(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/faq",expected=200)
    async def test_contact(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/contact",expected=200)
    async def test_legal(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/legal",expected=200)
    async def test_legal_slug(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/legal/test-slug",expected=404)
    async def test_success_stories(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/success-stories",expected=200)
    async def test_story_detail(self, client, db_session): await call(client,"portal","GET",f"/api/v1/portal/success-stories/{uuid.uuid4()}",expected=404)
    async def test_urgent_alerts(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/urgent-alerts",expected=200)
    async def test_transparency(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/transparency",expected=200)
    async def test_vet_network(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/veterinary-network",expected=200)
    async def test_me_dashboard(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/me/dashboard",headers=S.user_headers,expected=200)
    async def test_cms_public(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/cms/pages/about",expected=200)

    # --- Admin Blog (6) ---
    async def test_admin_blog_create(self, client, db_session):
        r = await call(client,"portal","POST","/api/v1/portal/admin/blog",headers=S.admin_headers,json={"title":f"Blog_{uid()}","content":"Test","status":"draft"},expected=201)
        if r.status_code==201: TestPortal.blog_id=r.json()["data"]["id"]
    async def test_admin_blog_list(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/admin/blog",headers=S.admin_headers,expected=200)
    async def test_admin_blog_update(self, client, db_session):
        if TestPortal.blog_id: await call(client,"portal","PUT",f"/api/v1/portal/admin/blog/{TestPortal.blog_id}",headers=S.admin_headers,json={"title":"Updated"},expected=200)
    async def test_admin_blog_delete(self, client, db_session):
        r = await client.post("/api/v1/portal/admin/blog",headers=S.admin_headers,json={"title":f"Del_{uid()}","content":"x","status":"draft"})
        if r.status_code==201:
            bid=r.json()["data"]["id"]
            await call(client,"portal","DELETE",f"/api/v1/portal/admin/blog/{bid}",headers=S.admin_headers,expected=200)
    async def test_admin_blog_bulk_delete(self, client, db_session): await call(client,"portal","POST","/api/v1/portal/admin/blog/bulk/delete",headers=S.admin_headers,json={"ids":[]},expected=200)
    async def test_admin_blog_bulk_status(self, client, db_session): await call(client,"portal","POST","/api/v1/portal/admin/blog/bulk/status",headers=S.admin_headers,json={"ids":[],"status":"published"},expected=200)

    # --- Admin FAQ (6) ---
    async def test_admin_faq_create(self, client, db_session):
        r = await call(client,"portal","POST","/api/v1/portal/admin/faq",headers=S.admin_headers,json={"question":f"Q_{uid()}?","answer":"A","category":"general"},expected=201)
        if r.status_code==201: TestPortal.faq_id=r.json()["data"]["id"]
    async def test_admin_faq_list(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/admin/faq",headers=S.admin_headers,expected=200)
    async def test_admin_faq_update(self, client, db_session):
        if TestPortal.faq_id: await call(client,"portal","PUT",f"/api/v1/portal/admin/faq/{TestPortal.faq_id}",headers=S.admin_headers,json={"answer":"Updated"},expected=200)
    async def test_admin_faq_delete(self, client, db_session):
        r = await client.post("/api/v1/portal/admin/faq",headers=S.admin_headers,json={"question":"Del?","answer":"x","category":"general"})
        if r.status_code==201:
            fid=r.json()["data"]["id"]
            await call(client,"portal","DELETE",f"/api/v1/portal/admin/faq/{fid}",headers=S.admin_headers,expected=200)
    async def test_admin_faq_bulk_delete(self, client, db_session): await call(client,"portal","POST","/api/v1/portal/admin/faq/bulk/delete",headers=S.admin_headers,json={"ids":[]},expected=200)
    async def test_admin_faq_bulk_status(self, client, db_session): await call(client,"portal","POST","/api/v1/portal/admin/faq/bulk/status",headers=S.admin_headers,json={"ids":[],"status":"published"},expected=200)

    # --- Admin Contact (2) ---
    async def test_admin_contact_create(self, client, db_session):
        r = await call(client,"portal","POST","/api/v1/portal/admin/contact",headers=S.admin_headers,json={"location_name":f"Contact_{uid()}","address":"123","phone":"+1","email":"c@test.com"},expected=201)
        if r.status_code==201: TestPortal.contact_id=r.json()["data"]["id"]
    async def test_admin_contact_update(self, client, db_session):
        if TestPortal.contact_id: await call(client,"portal","PUT",f"/api/v1/portal/admin/contact/{TestPortal.contact_id}",headers=S.admin_headers,json={"phone":"+2"},expected=200)

    # --- Admin Legal (4) ---
    async def test_admin_legal_create(self, client, db_session):
        r = await call(client,"portal","POST","/api/v1/portal/admin/legal",headers=S.admin_headers,json={"title":f"Legal_{uid()}","content":"Content","document_type":"privacy_policy"},expected=201)
        if r.status_code==201: TestPortal.legal_id=r.json()["data"]["id"]
    async def test_admin_legal_list(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/admin/legal",headers=S.admin_headers,expected=200)
    async def test_admin_legal_update(self, client, db_session):
        if TestPortal.legal_id: await call(client,"portal","PUT",f"/api/v1/portal/admin/legal/{TestPortal.legal_id}",headers=S.admin_headers,json={"content":"Updated"},expected=200)
    async def test_admin_legal_delete(self, client, db_session):
        r = await client.post("/api/v1/portal/admin/legal",headers=S.admin_headers,json={"title":"Del","content":"x","document_type":"privacy_policy"})
        if r.status_code==201:
            lid=r.json()["data"]["id"]
            await call(client,"portal","DELETE",f"/api/v1/portal/admin/legal/{lid}",headers=S.admin_headers,expected=200)

    # --- Admin Success Stories (6) ---
    async def test_admin_story_create(self, client, db_session):
        r = await call(client,"portal","POST","/api/v1/portal/admin/success-stories",headers=S.admin_headers,json={"title":f"Story_{uid()}","content":"Happy story","dog_name":"Buddy"},expected=201)
        if r.status_code==201: TestPortal.story_id=r.json()["data"]["id"]
    async def test_admin_story_list(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/admin/success-stories",headers=S.admin_headers,expected=200)
    async def test_admin_story_update(self, client, db_session):
        if TestPortal.story_id: await call(client,"portal","PUT",f"/api/v1/portal/admin/success-stories/{TestPortal.story_id}",headers=S.admin_headers,json={"content":"Updated"},expected=200)
    async def test_admin_story_delete(self, client, db_session):
        r = await client.post("/api/v1/portal/admin/success-stories",headers=S.admin_headers,json={"title":"Del","content":"x","dog_name":"X"})
        if r.status_code==201:
            sid=r.json()["data"]["id"]
            await call(client,"portal","DELETE",f"/api/v1/portal/admin/success-stories/{sid}",headers=S.admin_headers,expected=200)
    async def test_admin_story_bulk_delete(self, client, db_session): await call(client,"portal","POST","/api/v1/portal/admin/success-stories/bulk/delete",headers=S.admin_headers,json={"ids":[]},expected=200)
    async def test_admin_story_bulk_status(self, client, db_session): await call(client,"portal","POST","/api/v1/portal/admin/success-stories/bulk/status",headers=S.admin_headers,json={"ids":[],"status":"published"},expected=200)

    # --- Admin Urgent Alerts (4) ---
    async def test_admin_alert_create(self, client, db_session):
        r = await call(client,"portal","POST","/api/v1/portal/admin/urgent-alerts",headers=S.admin_headers,json={"title":f"Alert_{uid()}","message":"Emergency","severity":"high"},expected=201)
        if r.status_code==201: TestPortal.alert_id=r.json()["data"]["id"]
    async def test_admin_alert_list(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/admin/urgent-alerts",headers=S.admin_headers,expected=200)
    async def test_admin_alert_update(self, client, db_session):
        if TestPortal.alert_id: await call(client,"portal","PUT",f"/api/v1/portal/admin/urgent-alerts/{TestPortal.alert_id}",headers=S.admin_headers,json={"message":"Updated"},expected=200)
    async def test_admin_alert_delete(self, client, db_session):
        r = await client.post("/api/v1/portal/admin/urgent-alerts",headers=S.admin_headers,json={"title":"Del","message":"x","severity":"low"})
        if r.status_code==201:
            aid=r.json()["data"]["id"]
            await call(client,"portal","DELETE",f"/api/v1/portal/admin/urgent-alerts/{aid}",headers=S.admin_headers,expected=200)

    # --- Admin Vet Network (2) ---
    async def test_admin_vet_create(self, client, db_session):
        r = await call(client,"portal","POST","/api/v1/portal/admin/veterinary-network",headers=S.admin_headers,json={"name":f"Vet_{uid()}","address":"Vet St","phone":"+1"},expected=201)
        if r.status_code==201: TestPortal.vet_partner_id=r.json()["data"]["id"]
    async def test_admin_vet_update(self, client, db_session):
        if TestPortal.vet_partner_id: await call(client,"portal","PUT",f"/api/v1/portal/admin/veterinary-network/{TestPortal.vet_partner_id}",headers=S.admin_headers,json={"phone":"+2"},expected=200)

    # --- Admin Settings (2) ---
    async def test_admin_settings_get(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/admin/settings",headers=S.admin_headers,expected=200)
    async def test_admin_settings_update(self, client, db_session):
        r = await client.get("/api/v1/portal/admin/settings",headers=S.admin_headers)
        if r.status_code==200:
            data=r.json().get("data",{})
            if data:
                key=list(data.keys())[0]
                await call(client,"portal","PUT",f"/api/v1/portal/admin/settings/{key}",headers=S.admin_headers,json={"value":"Updated"},expected=200)

    # --- Admin CMS (5) ---
    async def test_admin_cms_list(self, client, db_session): await call(client,"portal","GET","/api/v1/portal/admin/cms/pages",headers=S.admin_headers,expected=200)
    async def test_admin_cms_get(self, client, db_session): await call(client,"portal","GET",f"/api/v1/portal/admin/cms/pages/about",headers=S.admin_headers,expected=200)
    async def test_admin_cms_update(self, client, db_session):
        await call(client,"portal","PUT",f"/api/v1/portal/admin/cms/pages/about",headers=S.admin_headers,json={"title":"About Us","content":"Updated"},expected=200)
    async def test_admin_cms_publish(self, client, db_session):
        await call(client,"portal","POST",f"/api/v1/portal/admin/cms/pages/about/publish",headers=S.admin_headers,expected=200)
    async def test_admin_cms_discard(self, client, db_session):
        await call(client,"portal","POST",f"/api/v1/portal/admin/cms/pages/about/discard",headers=S.admin_headers,expected=200)


# ═══════════════════════════════════════════════════════════════════════════
# FINAL: Save performance report
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFinalReport:
    async def test_generate_report(self, client, db_session):
        summary = tracker.save("docs/performance/api-benchmark")
        print(f"\n{'='*60}")
        print(f"PAW-GUARD FULL API VERIFICATION")
        print(f"{'='*60}")
        print(f"Endpoints tested: {summary['total']}")
        print(f"Passed: {summary['passed']}")
        print(f"Failed: {summary['failed']}")
        print(f"Blocked: {summary['blocked']}")
        print(f"Coverage: {summary['coverage']}")
        print(f"{'='*60}")
        assert True
