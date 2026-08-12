"""E2E tests for DONATIONS module (29 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestDonationEndpoints:
    """All 29 donation endpoints."""

    async def test_register_donor(self, client, setup):
        r = await call(client, "donations", "POST", "/api/v1/donations/register",
                       headers=setup.admin_headers, json={
                           "tax_identifier": f"TAX-{uid()}",
                           "notes": "Test donor",
                       }, expected=201)
        TEST.donor_id = uuid.UUID(r.json()["data"]["id"])

    async def test_create_donation(self, client, setup):
        r = await call(client, "donations", "POST", "/api/v1/donations",
                       headers=setup.admin_headers, json={
                           "amount": 100.0,
                           "currency": "INR",
                           "donation_type": "one_time",
                       }, expected=201)
        TEST.donation_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_donations(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations",
                       headers=setup.admin_headers, expected=200)

    async def test_donation_history(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations/history",
                       headers=setup.admin_headers, expected=200)

    async def test_checkout_donation(self, client, setup):
        r = await call(client, "donations", "POST", "/api/v1/donations/checkout",
                       headers=setup.admin_headers, json={
                           "amount": 250.0,
                           "currency": "INR",
                           "donation_type": "one_time",
                       }, expected=200)

    async def test_verify_donation(self, client, setup):
        r = await call(client, "donations", "POST", "/api/v1/donations/verify",
                       headers=setup.admin_headers, json={
                           "payment_id": f"pay_{uid()}",
                       }, expected=200)

    async def test_get_donation_receipt(self, client, setup):
        if TEST.donation_id:
            donation_id = str(TEST.donation_id)
        else:
            create_r = await client.post("/api/v1/donations", json={
                "amount": 50.0,
                "currency": "INR",
                "donation_type": "one_time",
            }, headers=setup.admin_headers)
            donation_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "GET",
                       f"/api/v1/donations/{donation_id}/receipt",
                       headers=setup.admin_headers, expected=200)

    async def test_reconcile_donation(self, client, setup):
        if TEST.donation_id:
            donation_id = str(TEST.donation_id)
        else:
            create_r = await client.post("/api/v1/donations", json={
                "amount": 75.0,
                "currency": "INR",
                "donation_type": "one_time",
            }, headers=setup.admin_headers)
            donation_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "POST",
                       f"/api/v1/donations/{donation_id}/reconcile",
                       headers=setup.admin_headers, json={
                           "reconciled": True,
                       }, expected=200)

    async def test_update_donation_status(self, client, setup):
        if TEST.donation_id:
            donation_id = str(TEST.donation_id)
        else:
            create_r = await client.post("/api/v1/donations", json={
                "amount": 30.0,
                "currency": "INR",
                "donation_type": "one_time",
            }, headers=setup.admin_headers)
            donation_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "PATCH",
                       f"/api/v1/donations/{donation_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "completed",
                       }, expected=200)

    # ── Campaigns ────────────────────────────────────────────────────────

    async def test_create_campaign(self, client, setup):
        r = await call(client, "donations", "POST", "/api/v1/donations/campaigns",
                       headers=setup.admin_headers, json={
                           "name": f"Campaign_{uid()}",
                           "description": "Test campaign",
                           "target_amount": 10000.0,
                           "currency": "INR",
                           "campaign_type": "general",
                           "status": "active",
                           "start_date": "2026-01-01",
                       }, expected=201)
        TEST.campaign_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_campaigns(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations/campaigns",
                       headers=setup.admin_headers, expected=200)

    async def test_manage_campaigns(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations/campaigns/manage",
                       headers=setup.admin_headers, expected=200)

    async def test_get_campaign(self, client, setup):
        if TEST.campaign_id:
            campaign_id = str(TEST.campaign_id)
        else:
            create_r = await client.post("/api/v1/donations/campaigns", json={
                "name": f"Campaign_{uid()}",
                "description": "Get campaign",
                "target_amount": 5000.0,
                "currency": "INR",
                "campaign_type": "medical",
                "status": "active",
                "start_date": "2026-02-01",
            }, headers=setup.admin_headers)
            campaign_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "GET",
                       f"/api/v1/donations/campaigns/{campaign_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_update_campaign(self, client, setup):
        if TEST.campaign_id:
            campaign_id = str(TEST.campaign_id)
        else:
            create_r = await client.post("/api/v1/donations/campaigns", json={
                "name": f"Campaign_{uid()}",
                "description": "Update campaign",
                "target_amount": 8000.0,
                "currency": "INR",
                "campaign_type": "general",
                "status": "active",
                "start_date": "2026-03-01",
            }, headers=setup.admin_headers)
            campaign_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "PATCH",
                       f"/api/v1/donations/campaigns/{campaign_id}",
                       headers=setup.admin_headers, json={
                           "target_amount": 15000.0,
                       }, expected=200)

    async def test_delete_campaign(self, client, setup):
        create_r = await client.post("/api/v1/donations/campaigns", json={
            "name": f"DelCampaign_{uid()}",
            "description": "To delete",
            "target_amount": 1000.0,
            "currency": "INR",
            "campaign_type": "general",
            "status": "draft",
            "start_date": "2026-04-01",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            campaign_id = create_r.json()["data"]["id"]
            r = await call(client, "donations", "DELETE",
                           f"/api/v1/donations/campaigns/{campaign_id}",
                           headers=setup.admin_headers, expected=200)

    # ── Donors ───────────────────────────────────────────────────────────

    async def test_list_donors(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations/donors",
                       headers=setup.admin_headers, expected=200)

    async def test_my_donor_profile(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations/donors/me",
                       headers=setup.admin_headers, expected=200)

    async def test_update_donor(self, client, setup):
        if TEST.donor_id:
            donor_id = str(TEST.donor_id)
        else:
            create_r = await client.post("/api/v1/donations/register", json={
                "tax_identifier": f"TAX-{uid()}",
                "notes": "Update donor",
            }, headers=setup.admin_headers)
            donor_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "PUT",
                       f"/api/v1/donations/donors/{donor_id}",
                       headers=setup.admin_headers, json={
                           "notes": "Updated donor notes",
                       }, expected=200)

    async def test_delete_donor(self, client, setup):
        create_r = await client.post("/api/v1/donations/register", json={
            "tax_identifier": f"TAX-{uid()}",
            "notes": "Del donor",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            donor_id = create_r.json()["data"]["id"]
            r = await call(client, "donations", "DELETE",
                           f"/api/v1/donations/donors/{donor_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_donors(self, client, setup):
        create_r = await client.post("/api/v1/donations/register", json={
            "tax_identifier": f"TAX-{uid()}",
            "notes": "Bulk del donor",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            donor_id = create_r.json()["data"]["id"]
            r = await call(client, "donations", "POST",
                           "/api/v1/donations/donors/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [donor_id],
                           }, expected=200)

    # ── Recurring ────────────────────────────────────────────────────────

    async def test_create_recurring(self, client, setup):
        r = await call(client, "donations", "POST", "/api/v1/donations/recurring",
                       headers=setup.admin_headers, json={
                           "amount": 500.0,
                           "currency": "INR",
                           "frequency": "monthly",
                       }, expected=201)
        TEST.recurring_sub_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_recurring(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations/recurring",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_recurring(self, client, setup):
        if TEST.recurring_sub_id:
            sub_id = str(TEST.recurring_sub_id)
        else:
            create_r = await client.post("/api/v1/donations/recurring", json={
                "amount": 200.0,
                "currency": "INR",
                "frequency": "weekly",
            }, headers=setup.admin_headers)
            sub_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "DELETE",
                       f"/api/v1/donations/recurring/{sub_id}",
                       headers=setup.admin_headers, expected=200)

    # ── Sponsorships ─────────────────────────────────────────────────────

    async def test_create_sponsorship(self, client, setup):
        r = await call(client, "donations", "POST", "/api/v1/donations/sponsorships",
                       headers=setup.admin_headers, json={
                           "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                           "amount": 1000.0,
                           "currency": "INR",
                           "frequency": "monthly",
                       }, expected=201)
        TEST.sponsorship_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_sponsorships(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations/sponsorships",
                       headers=setup.admin_headers, expected=200)

    async def test_my_sponsorships(self, client, setup):
        r = await call(client, "donations", "GET", "/api/v1/donations/sponsorships/my",
                       headers=setup.admin_headers, expected=200)

    async def test_get_sponsorship(self, client, setup):
        if TEST.sponsorship_id:
            sp_id = str(TEST.sponsorship_id)
        else:
            create_r = await client.post("/api/v1/donations/sponsorships", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "amount": 500.0,
                "currency": "INR",
                "frequency": "yearly",
            }, headers=setup.admin_headers)
            sp_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "GET",
                       f"/api/v1/donations/sponsorships/{sp_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_update_sponsorship_status(self, client, setup):
        if TEST.sponsorship_id:
            sp_id = str(TEST.sponsorship_id)
        else:
            create_r = await client.post("/api/v1/donations/sponsorships", json={
                "dog_id": str(TEST.dog_ids[0]) if TEST.dog_ids else str(uuid.uuid4()),
                "amount": 300.0,
                "currency": "INR",
                "frequency": "monthly",
            }, headers=setup.admin_headers)
            sp_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "PATCH",
                       f"/api/v1/donations/sponsorships/{sp_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "active",
                       }, expected=200)

    async def test_bulk_status_update_donations(self, client, setup):
        if TEST.donation_id:
            donation_id = str(TEST.donation_id)
        else:
            create_r = await client.post("/api/v1/donations", json={
                "amount": 10.0,
                "currency": "INR",
                "donation_type": "one_time",
            }, headers=setup.admin_headers)
            donation_id = create_r.json()["data"]["id"]
        r = await call(client, "donations", "POST",
                       "/api/v1/donations/bulk/status-update",
                       headers=setup.admin_headers, json={
                           "ids": [donation_id],
                           "status": "completed",
                       }, expected=200)
