"""Dependency-aware test data factories for all PAW-GUARD modules.

Creates prerequisite records in correct order:
  auth -> users -> dogs -> rescue -> foster -> adoption -> medical -> etc.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth


class TestData:
    """Shared mutable state across test modules."""

    def __init__(self):
        self.admin_headers: dict = {}
        self.admin_user_id: uuid.UUID | None = None
        self.staff_headers: dict = {}
        self.staff_user_id: uuid.UUID | None = None
        self.user_headers: dict = {}
        self.user_id: uuid.UUID | None = None
        self.vet_headers: dict = {}
        self.vet_user_id: uuid.UUID | None = None
        self.dog_ids: list[uuid.UUID] = []
        self.facility_id: uuid.UUID | None = None
        self.section_id: uuid.UUID | None = None
        self.kennel_id: uuid.UUID | None = None
        self.rescue_request_id: uuid.UUID | None = None
        self.dispatch_id: uuid.UUID | None = None
        self.foster_profile_id: uuid.UUID | None = None
        self.adoption_app_id: uuid.UUID | None = None
        self.donor_id: uuid.UUID | None = None
        self.donation_id: uuid.UUID | None = None
        self.campaign_id: uuid.UUID | None = None
        self.sponsorship_id: uuid.UUID | None = None
        self.volunteer_profile_id: uuid.UUID | None = None
        self.shift_id: uuid.UUID | None = None
        self.inventory_item_id: uuid.UUID | None = None
        self.requisition_id: uuid.UUID | None = None
        self.finance_account_debit_id: uuid.UUID | None = None
        self.finance_account_credit_id: uuid.UUID | None = None
        self.transaction_id: uuid.UUID | None = None
        self.budget_id: uuid.UUID | None = None
        self.vehicle_id: uuid.UUID | None = None
        self.companion_pet_id: uuid.UUID | None = None
        self.vet_clinic_id: uuid.UUID | None = None
        self.appointment_id: uuid.UUID | None = None
        self.prescription_id: uuid.UUID | None = None
        self.lost_report_id: uuid.UUID | None = None
        self.found_report_id: uuid.UUID | None = None
        self.match_id: uuid.UUID | None = None
        self.grievance_ticket_id: uuid.UUID | None = None
        self.feedback_id: uuid.UUID | None = None
        self.notification_id: uuid.UUID | None = None
        self.storage_file_id: uuid.UUID | None = None
        self.role_id: uuid.UUID | None = None
        self.recurring_sub_id: uuid.UUID | None = None
        self.recurring_tx_id: uuid.UUID | None = None
        self.equipment_checkout_id: uuid.UUID | None = None
        self.fuel_log_id: uuid.UUID | None = None
        self.placement_id: uuid.UUID | None = None


TEST = TestData()


async def setup_admin_user(client: AsyncClient, db: AsyncSession) -> dict:
    """Register + promote user to super_admin. Returns Bearer headers."""
    email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    headers = await register_and_auth(client, db, email=email, role="super_admin")
    TEST.admin_headers = headers
    return headers


async def setup_staff_user(client: AsyncClient, db: AsyncSession) -> dict:
    """Register + promote user to shelter_manager role."""
    email = f"staff_{uuid.uuid4().hex[:8]}@test.com"
    headers = await register_and_auth(client, db, email=email, role="shelter_manager")
    TEST.staff_headers = headers
    return headers


async def setup_regular_user(client: AsyncClient, db: AsyncSession) -> dict:
    """Register a regular authenticated user."""
    email = f"user_{uuid.uuid4().hex[:8]}@test.com"
    headers = await register_and_auth(client, db, email=email, role="volunteer")
    TEST.user_headers = headers
    return headers


async def setup_vet_user(client: AsyncClient, db: AsyncSession) -> dict:
    """Register + promote user to veterinarian (required for medical clearance)."""
    email = f"vet_{uuid.uuid4().hex[:8]}@test.com"
    headers = await register_and_auth(client, db, email=email, role="veterinarian")
    TEST.vet_headers = headers
    return headers


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def create_dog(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "name": f"Buddy_{_uid()}",
        "breed": "indie_mix",
        "gender": "male",
        "age_months": 24,
        "weight": 15.0,
        "color": "brown",
        "temperament": "friendly",
        "is_adoptable": True,
        "is_quarantine_passed": True,
    }
    r = await client.post("/api/v1/dogs", json=payload, headers=headers)
    if r.status_code == 201:
        data = r.json()["data"]
        TEST.dog_ids.append(uuid.UUID(data["id"]))
        return data
    return {}


async def create_facility(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "name": f"Shelter_{_uid()}",
        "address": "123 Rescue Lane",
        "phone": "+1234567890",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "total_capacity": 50,
        "facility_type": "shelter",
    }
    r = await client.post("/api/v1/shelter/facilities", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.facility_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_section(client: AsyncClient, headers: dict, facility_id: str) -> dict:
    payload = {
        "name": f"Section_{_uid()}",
        "section_type": "general",
        "capacity": 10,
    }
    r = await client.post(
        f"/api/v1/shelter/facilities/{facility_id}/sections",
        json=payload,
        headers=headers,
    )
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.section_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_kennel(client: AsyncClient, headers: dict, section_id: str) -> dict:
    payload = {"identifier": f"K-{_uid()}", "capacity": 1}
    r = await client.post(
        f"/api/v1/shelter/sections/{section_id}/kennels",
        json=payload,
        headers=headers,
    )
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.kennel_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_rescue_request(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "reporter_name": f"Reporter_{_uid()}",
        "reporter_phone": "+9876543210",
        "location_address": "456 Emergency Road",
        "animal_count": 1,
        "physical_condition": "injured",
        "severity": "high",
        "is_urgent": False,
    }
    r = await client.post("/api/v1/rescue/report", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.rescue_request_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_dispatch(client: AsyncClient, headers: dict, request_id: str) -> dict:
    payload = {"notes": "Deploying team"}
    r = await client.post(
        f"/api/v1/rescue/{request_id}/dispatch",
        json=payload,
        headers=headers,
    )
    if r.status_code in (200, 201):
        data = r.json().get("data", {})
        if data:
            TEST.dispatch_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_foster_profile(client: AsyncClient, headers: dict) -> dict:
    payload = {"max_capacity": 3, "preferences": "dogs"}
    r = await client.post("/api/v1/fosters/apply", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.foster_profile_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_adoption(client: AsyncClient, headers: dict, dog_id: str) -> dict:
    payload = {
        "dog_id": dog_id,
        "residential_status": "owned",
        "has_landlord_approval": True,
        "has_yard_fence": True,
        "household_members_count": 3,
        "pet_care_experience": "5 years",
    }
    r = await client.post("/api/v1/adoptions", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.adoption_app_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_donor(client: AsyncClient, headers: dict) -> dict:
    payload = {"tax_identifier": f"TAX-{_uid()}", "notes": "Test donor"}
    r = await client.post("/api/v1/donations/register", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.donor_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_donation(client: AsyncClient, headers: dict) -> dict:
    payload = {"amount": 100.0, "currency": "INR", "donation_type": "one_time"}
    r = await client.post("/api/v1/donations", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.donation_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_campaign(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "name": f"Campaign_{_uid()}",
        "description": "Test campaign",
        "target_amount": 10000.0,
        "currency": "INR",
        "campaign_type": "general",
        "status": "active",
        "start_date": date.today().isoformat(),
    }
    r = await client.post("/api/v1/donations/campaigns", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.campaign_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_volunteer(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "emergency_contact_name": "Emergency Contact",
        "emergency_contact_phone": "+1234567890",
        "skills": "animal care",
        "availability": "weekends",
    }
    r = await client.post("/api/v1/volunteers/apply", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.volunteer_profile_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_shift(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "role_name": "dog_walker",
        "start_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "end_at": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
        "capacity": 5,
    }
    r = await client.post("/api/v1/volunteers/shifts", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.shift_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_inventory_item(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "name": f"Item_{_uid()}",
        "category": "food",
        "quantity": 100.0,
        "unit": "kg",
        "reorder_threshold": 10.0,
        "unit_cost": 5.0,
    }
    r = await client.post("/api/v1/inventory/items", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.inventory_item_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_finance_accounts(client: AsyncClient, headers: dict) -> dict:
    debit = {
        "account_code": f"100{_uid()[:4]}",
        "account_name": f"Cash_{_uid()}",
        "account_type": "asset",
        "category": "cash",
        "opening_balance": "10000.00",
    }
    r1 = await client.post("/api/v1/finance/accounts", json=debit, headers=headers)
    credit = {
        "account_code": f"200{_uid()[:4]}",
        "account_name": f"Donations_{_uid()}",
        "account_type": "income",
        "category": "donation_income",
        "opening_balance": "0.00",
    }
    r2 = await client.post("/api/v1/finance/accounts", json=credit, headers=headers)
    if r1.status_code in (200, 201):
        TEST.finance_account_debit_id = uuid.UUID(r1.json()["data"]["id"])
    if r2.status_code in (200, 201):
        TEST.finance_account_credit_id = uuid.UUID(r2.json()["data"]["id"])
    return {}


async def create_vehicle(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "make_model": f"Toyota_{_uid()}",
        "license_plate": f"DL-{_uid()[:4]}",
        "vehicle_type": "rescue_van",
        "status": "active",
        "mileage": 5000,
    }
    r = await client.post("/api/v1/fleet/vehicles", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.vehicle_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_companion_pet(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "name": f"Whiskers_{_uid()}",
        "species": "cat",
        "breed": "persian",
        "date_of_birth": "2022-01-15",
        "gender": "female",
        "weight": 4.5,
    }
    r = await client.post("/api/v1/companion-pets", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.companion_pet_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_vet_clinic(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "name": f"VetClinic_{_uid()}",
        "address": "789 Vet Street",
        "phone": "+1122334455",
        "latitude": 28.6139,
        "longitude": 77.2090,
    }
    r = await client.post("/api/v1/companion-pets/clinics", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.vet_clinic_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_lost_report(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "pet_name": f"LostPet_{_uid()}",
        "species": "dog",
        "breed": "labrador",
        "color": "golden",
        "last_seen_location": "123 Main St",
        "last_seen_date": datetime.now(UTC).isoformat(),
        "description": "Friendly golden retriever",
        "contact_phone": "+9876543210",
    }
    r = await client.post("/api/v1/lost-found/lost", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.lost_report_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_found_report(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "species": "dog",
        "breed": "mixed",
        "color": "brown",
        "found_location": "456 Oak Ave",
        "found_date": datetime.now(UTC).isoformat(),
        "description": "Stray dog found near park",
        "contact_phone": "+9876543211",
    }
    r = await client.post("/api/v1/lost-found/found", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.found_report_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_grievance(client: AsyncClient) -> dict:
    payload = {
        "reporter_name": f"Reporter_{_uid()}",
        "reporter_phone": "+9876543210",
        "complaint_type": "service_quality",
        "details": "Test grievance details",
    }
    r = await client.post("/api/v1/grievance", json=payload)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.grievance_ticket_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_feedback(client: AsyncClient) -> dict:
    payload = {"rating": 5, "comments": "Great service!"}
    r = await client.post("/api/v1/grievance/feedback", json=payload)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.feedback_id = uuid.UUID(data["id"])
        return data
    return {}


async def create_storage_file(client: AsyncClient, headers: dict) -> dict:
    payload = {
        "filename": f"test_{_uid()}.jpg",
        "mime_type": "image/jpeg",
        "file_size": 1024,
        "folder": "test",
    }
    r = await client.post("/api/v1/storage/upload-url", json=payload, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()["data"]
        TEST.storage_file_id = uuid.UUID(data["id"])
        return data
    return {}


async def setup_all_prerequisites(client: AsyncClient, db: AsyncSession) -> None:
    """Create all prerequisite data for full E2E testing."""
    # 1. Auth users
    await setup_admin_user(client, db)
    await setup_staff_user(client, db)
    await setup_regular_user(client, db)
    await setup_vet_user(client, db)

    # 2. Facility + Section + Kennel
    fac = await create_facility(client, TEST.admin_headers)
    if fac:
        sec = await create_section(client, TEST.admin_headers, fac["id"])
        if sec:
            await create_kennel(client, TEST.admin_headers, sec["id"])

    # 3. Dog
    dog = await create_dog(client, TEST.admin_headers)
    if not dog:
        dog = await create_dog(client, TEST.staff_headers)

    # 4. Inventory
    await create_inventory_item(client, TEST.admin_headers)

    # 5. Finance accounts
    await create_finance_accounts(client, TEST.admin_headers)

    # 6. Vehicle
    await create_vehicle(client, TEST.admin_headers)

    # 7. Vet clinic
    await create_vet_clinic(client, TEST.admin_headers)

    # 8. Campaign
    await create_campaign(client, TEST.admin_headers)

    # 9. Donor
    await create_donor(client, TEST.admin_headers)
