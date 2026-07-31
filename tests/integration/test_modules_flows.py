"""Integration tests for end-to-end flows of all core modules."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.adoption.models import AdoptionStatus
from pawguard.modules.auth.models import Role, User
from pawguard.modules.dog.models import DogStatus
from pawguard.modules.lost_found.models import MatchStatus
from pawguard.modules.rescue.models import RescueStatus

REGISTER_PAYLOAD = {
    "email": "flowuser@example.com",
    "password": "StrongP@ss99",
    "full_name": "Flow User",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "flowuser@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestEndToEndModuleFlows:
    async def test_complete_pawguard_operations_flow(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # 1. Register & Login User
        reg_resp = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        assert reg_resp.status_code == 201

        # 2. Promote user to super_admin in DB
        stmt_user = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == REGISTER_PAYLOAD["email"])
        )
        user = (await db_session.execute(stmt_user)).scalar_one()

        stmt_role = select(Role).where(Role.name == "super_admin")
        super_admin_role = (await db_session.execute(stmt_role)).scalar_one()

        user.roles.append(super_admin_role)
        user.is_verified = True
        await db_session.commit()

        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        assert login_resp.status_code == 200
        token = login_resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Emergency Rescue Flow
        report_payload = {
            "reporter_name": "John Doe",
            "reporter_phone": "+9876543210",
            "location_address": "Street 10, Sector 4",
            "location_landmark": "Near Central Park",
            "latitude": 17.4482,
            "longitude": 78.3741,
            "physical_condition": "Injured/Fractured",
            "animal_count": 1,
        }
        rescue_resp = await client.post("/api/v1/rescue/report", json=report_payload)
        assert rescue_resp.status_code == 201
        case_data = rescue_resp.json()["data"]
        case_id = case_data["id"]
        assert case_data["status"] == RescueStatus.REPORTED.value
        assert "RES-" in case_data["ticket_number"]

        # Verify
        verify_payload = {"status": "verified"}
        verify_resp = await client.post(
            f"/api/v1/rescue/{case_id}/verify", json=verify_payload, headers=headers
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["data"]["status"] == RescueStatus.VERIFIED.value

        # Dispatch
        dispatch_payload = {
            "assigned_driver_id": str(user.id),
            "vehicle_id": "VAN-001",
            "equipment_details": "Cage, Net Gun",
        }
        dispatch_resp = await client.post(
            f"/api/v1/rescue/{case_id}/dispatch", json=dispatch_payload, headers=headers
        )
        assert dispatch_resp.status_code == 200
        assert dispatch_resp.json()["data"]["status"] == RescueStatus.DISPATCHED.value

        # Located
        located_resp = await client.post(
            f"/api/v1/rescue/{case_id}/located", headers=headers
        )
        assert located_resp.status_code == 200
        assert located_resp.json()["data"]["status"] == RescueStatus.LOCATED.value

        # Secured
        secured_resp = await client.post(
            f"/api/v1/rescue/{case_id}/secured", headers=headers
        )
        assert secured_resp.status_code == 200
        assert secured_resp.json()["data"]["status"] == RescueStatus.RESCUED.value

        # Admitted
        admit_payload = {
            "notes": "Animal admitted safely. Showing mild lacerations.",
            "photos": ["http://example.com/photo1.jpg"],
        }
        admit_resp = await client.post(
            f"/api/v1/rescue/{case_id}/admitted", json=admit_payload, headers=headers
        )
        assert admit_resp.status_code == 200
        assert admit_resp.json()["data"]["status"] == RescueStatus.ADMITTED.value

        # 4. Dog Management Flow
        # Register a dog profile
        dog_payload = {
            "rescue_case_id": case_id,
            "name": "Barnaby",
            "breed": "Indie Mix",
            "gender": "male",
            "estimated_age": "2 years",
            "weight": 15.4,
            "color": "brown",
            "temperament": "friendly",
            "is_adoptable": True,
            "is_quarantine_passed": True,
        }
        dog_resp = await client.post("/api/v1/dogs", json=dog_payload, headers=headers)
        assert dog_resp.status_code == 201
        dog_data = dog_resp.json()["data"]
        dog_id = dog_data["id"]
        assert dog_data["name"] == "Barnaby"
        assert dog_data["status"] == DogStatus.RESCUED.value
        # is_adoptable is always forced False at registration regardless of
        # payload; it can only be granted via vet-authorized medical clearance.
        assert dog_data["is_adoptable"] is False

        # 4b. Medical clearance (required before a dog can be adopted)
        clearance_resp = await client.post(
            f"/api/v1/medical/clearance/{dog_id}", headers=headers
        )
        assert clearance_resp.status_code == 200

        # 5. Adoption Flow
        adopt_payload = {
            "dog_id": dog_id,
            "residential_status": "owned",
            "has_landlord_approval": True,
            "has_yard_fence": True,
            "household_members_count": 3,
            "pet_care_experience": "Owned a dog previously for 10 years",
        }
        # Apply
        apply_resp = await client.post("/api/v1/adoptions", json=adopt_payload, headers=headers)
        assert apply_resp.status_code == 201
        app_data = apply_resp.json()["data"]
        app_id = app_data["id"]
        assert app_data["status"] == AdoptionStatus.SUBMITTED.value

        # Walk the vetting pipeline (submitted -> vetting -> home_check ->
        # approved) - status is a state machine, no direct jumps allowed.
        vetting_resp = await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "vetting"}, headers=headers
        )
        assert vetting_resp.status_code == 200

        # Home inspection approval is where exclusivity locks the dog, per
        # the PRR (not final approval).
        home_check_resp = await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "home_check"}, headers=headers
        )
        assert home_check_resp.status_code == 200
        get_dog_resp = await client.get(f"/api/v1/dogs/{dog_id}", headers=headers)
        assert get_dog_resp.json()["data"]["is_adoptable"] is False

        # Attempt secondary application (should fail/raise conflict, since the
        # dog is already locked at home_check)
        second_apply_resp = await client.post("/api/v1/adoptions", json=adopt_payload, headers=headers)
        assert second_apply_resp.status_code == 409

        approve_resp = await client.put(
            f"/api/v1/adoptions/{app_id}", json={"status": "approved"}, headers=headers
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["data"]["status"] == AdoptionStatus.APPROVED.value

        # Complete adoption
        complete_payload = {"status": "completed"}
        complete_resp = await client.put(
            f"/api/v1/adoptions/{app_id}", json=complete_payload, headers=headers
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["data"]["status"] == AdoptionStatus.COMPLETED.value

        # 6. Volunteer Flow
        vol_payload = {
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_phone": "+9876543210",
            "skills": "Animal handling, grooming",
            "availability": "weekends",
        }
        vol_resp = await client.post("/api/v1/volunteers/apply", json=vol_payload, headers=headers)
        assert vol_resp.status_code == 201
        vol_profile_id = vol_resp.json()["data"]["id"]

        # Approve/Onboard volunteer
        onboard_payload = {"status": "active"}
        onboard_resp = await client.put(
            f"/api/v1/volunteers/{vol_profile_id}", json=onboard_payload, headers=headers
        )
        assert onboard_resp.status_code == 200

        # Create Shift
        shift_payload = {
            "role_name": "feeding",
            "start_at": "2026-07-30T09:00:00Z",
            "end_at": "2026-07-30T13:00:00Z",
            "capacity": 5,
        }
        shift_resp = await client.post("/api/v1/volunteers/shifts", json=shift_payload, headers=headers)
        assert shift_resp.status_code == 201
        shift_id = shift_resp.json()["data"]["id"]

        # Join shift
        join_resp = await client.post(f"/api/v1/volunteers/shifts/{shift_id}/join", headers=headers)
        assert join_resp.status_code == 200
        attendance_id = join_resp.json()["data"]["id"]

        # Check-in
        check_in_resp = await client.post(
            f"/api/v1/volunteers/attendance/{attendance_id}/check-in", headers=headers
        )
        assert check_in_resp.status_code == 200

        # Check-out
        check_out_resp = await client.post(
            f"/api/v1/volunteers/attendance/{attendance_id}/check-out", headers=headers
        )
        assert check_out_resp.status_code == 200
        assert check_out_resp.json()["data"]["hours_logged"] is not None

        # 7. Foster Flow
        foster_payload = {
            "preferences": "Pups, recovery",
            "max_capacity": 2,
            "notes": "Spacious apartment",
        }
        foster_resp = await client.post("/api/v1/fosters/apply", json=foster_payload, headers=headers)
        assert foster_resp.status_code == 201
        foster_profile_id = foster_resp.json()["data"]["id"]

        # Approve foster
        approve_foster_payload = {"status": "approved"}
        approve_foster_resp = await client.put(
            f"/api/v1/fosters/{foster_profile_id}", json=approve_foster_payload, headers=headers
        )
        assert approve_foster_resp.status_code == 200

        # Reset dog adoptable status for foster test
        update_dog_payload = {"status": "shelter"}
        await client.put(f"/api/v1/dogs/{dog_id}", json=update_dog_payload, headers=headers)

        # Place dog in foster care
        placement_payload = {
            "dog_id": dog_id,
            "notes": "Placing for recovery care",
        }
        place_resp = await client.post(
            f"/api/v1/fosters/{foster_profile_id}/placements", json=placement_payload, headers=headers
        )
        assert place_resp.status_code == 201
        placement_id = place_resp.json()["data"]["id"]

        # Return dog from foster care
        return_resp = await client.post(
            f"/api/v1/fosters/placements/{placement_id}/return", json={"notes": "Returned healthy"}, headers=headers
        )
        assert return_resp.status_code == 200

        # 8. Donation Flow
        donor_reg_payload = {"tax_identifier": "TAX-123456", "notes": "Regular corporate donor"}
        donor_reg_resp = await client.post("/api/v1/donations/register", json=donor_reg_payload, headers=headers)
        assert donor_reg_resp.status_code == 201

        donation_payload = {
            "dog_id": dog_id,
            "amount": 250.00,
            "currency": "USD",
            "donation_type": "sponsorship",
            "notes": "Barnaby recovery fund sponsorship",
        }
        donate_resp = await client.post("/api/v1/donations", json=donation_payload, headers=headers)
        assert donate_resp.status_code == 201
        assert donate_resp.json()["data"]["status"] == "success"

        history_resp = await client.get("/api/v1/donations/history", headers=headers)
        assert history_resp.status_code == 200
        assert len(history_resp.json()["data"]) >= 1

        # 9. Lost & Found Proximity Matching Flow
        lost_payload = {
            "pet_name": "Max",
            "breed": "Beagle Mix",
            "color": "Brown/Black",
            "location_address": "Road No 5, Jubilee Hills",
            "latitude": 17.4285,
            "longitude": 78.4020,
            "lost_at": "2026-07-28T10:00:00Z",
        }
        lost_resp = await client.post("/api/v1/lost-found/lost", json=lost_payload, headers=headers)
        assert lost_resp.status_code == 201
        lost_id = lost_resp.json()["data"]["id"]

        found_payload = {
            "breed_observed": "Beagle Mix",
            "color_observed": "Brown/Black",
            "location_address": "Road No 6, Jubilee Hills",  # very close proximity
            "latitude": 17.4290,
            "longitude": 78.4025,
            "found_at": "2026-07-28T11:00:00Z",
        }
        found_resp = await client.post("/api/v1/lost-found/found", json=found_payload, headers=headers)
        assert found_resp.status_code == 201
        found_resp.json()["data"]["id"]

        # View matches
        matches_resp = await client.get(f"/api/v1/lost-found/lost/{lost_id}/matches", headers=headers)
        assert matches_resp.status_code == 200
        matches = matches_resp.json()["data"]
        assert len(matches) >= 1
        match_id = matches[0]["id"]
        assert matches[0]["confidence_score"] > 50.0

        # Resolve match
        resolve_resp = await client.post(
            f"/api/v1/lost-found/matches/{match_id}/resolve?approve=true", headers=headers
        )
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["data"]["status"] == MatchStatus.CONFIRMED.value
