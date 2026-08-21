"""E2E tests for FLEET module (17 endpoints)."""

import uuid

import pytest
from tests.e2e.factories import TEST
from tests.e2e.helpers import call, uid


@pytest.mark.asyncio
class TestFleetEndpoints:
    """All 17 fleet endpoints."""

    async def test_create_vehicle(self, client, setup):
        r = await call(
            client,
            "fleet",
            "POST",
            "/api/v1/fleet/vehicles",
            headers=setup.admin_headers,
            json={
                "make_model": f"Toyota_{uid()}",
                "license_plate": f"DL-{uid()[:4]}",
                "vehicle_type": "rescue_van",
                "status": "active",
                "mileage": 5000,
            },
            expected=201,
        )
        TEST.vehicle_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_vehicles(self, client, setup):
        await call(
            client,
            "fleet",
            "GET",
            "/api/v1/fleet/vehicles",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_get_vehicle(self, client, setup):
        if TEST.vehicle_id:
            vehicle_id = str(TEST.vehicle_id)
        else:
            create_r = await client.post(
                "/api/v1/fleet/vehicles",
                json={
                    "make_model": f"Honda_{uid()}",
                    "license_plate": f"MH-{uid()[:4]}",
                    "vehicle_type": "ambulance",
                    "status": "active",
                    "mileage": 12000,
                },
                headers=setup.admin_headers,
            )
            vehicle_id = create_r.json()["data"]["id"]
        await call(
            client,
            "fleet",
            "GET",
            f"/api/v1/fleet/vehicles/{vehicle_id}",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_vehicle(self, client, setup):
        if TEST.vehicle_id:
            vehicle_id = str(TEST.vehicle_id)
        else:
            create_r = await client.post(
                "/api/v1/fleet/vehicles",
                json={
                    "make_model": f"Ford_{uid()}",
                    "license_plate": f"UP-{uid()[:4]}",
                    "vehicle_type": "truck",
                    "status": "active",
                    "mileage": 8000,
                },
                headers=setup.admin_headers,
            )
            vehicle_id = create_r.json()["data"]["id"]
        await call(
            client,
            "fleet",
            "PUT",
            f"/api/v1/fleet/vehicles/{vehicle_id}",
            headers=setup.admin_headers,
            json={
                "mileage": 9000,
            },
            expected=200,
        )

    async def test_delete_vehicle(self, client, setup):
        create_r = await client.post(
            "/api/v1/fleet/vehicles",
            json={
                "make_model": f"Del_{uid()}",
                "license_plate": f"KA-{uid()[:4]}",
                "vehicle_type": "van",
                "status": "inactive",
                "mileage": 20000,
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            vehicle_id = create_r.json()["data"]["id"]
            await call(
                client,
                "fleet",
                "DELETE",
                f"/api/v1/fleet/vehicles/{vehicle_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_update_vehicle_status(self, client, setup):
        if TEST.vehicle_id:
            vehicle_id = str(TEST.vehicle_id)
        else:
            create_r = await client.post(
                "/api/v1/fleet/vehicles",
                json={
                    "make_model": f"Status_{uid()}",
                    "license_plate": f"TN-{uid()[:4]}",
                    "vehicle_type": "car",
                    "status": "active",
                    "mileage": 3000,
                },
                headers=setup.admin_headers,
            )
            vehicle_id = create_r.json()["data"]["id"]
        await call(
            client,
            "fleet",
            "PATCH",
            f"/api/v1/fleet/vehicles/{vehicle_id}/status",
            headers=setup.admin_headers,
            json={
                "status": "maintenance",
            },
            expected=200,
        )

    async def test_add_fuel_log(self, client, setup):
        if TEST.vehicle_id:
            vehicle_id = str(TEST.vehicle_id)
        else:
            create_r = await client.post(
                "/api/v1/fleet/vehicles",
                json={
                    "make_model": f"Fuel_{uid()}",
                    "license_plate": f"GJ-{uid()[:4]}",
                    "vehicle_type": "van",
                    "status": "active",
                    "mileage": 7000,
                },
                headers=setup.admin_headers,
            )
            vehicle_id = create_r.json()["data"]["id"]
        r = await call(
            client,
            "fleet",
            "POST",
            f"/api/v1/fleet/vehicles/{vehicle_id}/fuel",
            headers=setup.admin_headers,
            json={
                "liters": 40.0,
                "cost": 3600.0,
                "odometer": 7500,
            },
            expected=201,
        )
        TEST.fuel_log_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_fuel_logs(self, client, setup):
        if TEST.vehicle_id:
            vehicle_id = str(TEST.vehicle_id)
        else:
            create_r = await client.post(
                "/api/v1/fleet/vehicles",
                json={
                    "make_model": f"FuelList_{uid()}",
                    "license_plate": f"RJ-{uid()[:4]}",
                    "vehicle_type": "truck",
                    "status": "active",
                    "mileage": 15000,
                },
                headers=setup.admin_headers,
            )
            vehicle_id = create_r.json()["data"]["id"]
        await call(
            client,
            "fleet",
            "GET",
            f"/api/v1/fleet/vehicles/{vehicle_id}/fuel",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_get_fuel_log(self, client, setup):
        log_id = str(TEST.fuel_log_id) if TEST.fuel_log_id else str(uuid.uuid4())
        await call(
            client,
            "fleet",
            "GET",
            f"/api/v1/fleet/fuel/{log_id}",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_add_maintenance(self, client, setup):
        if TEST.vehicle_id:
            vehicle_id = str(TEST.vehicle_id)
        else:
            create_r = await client.post(
                "/api/v1/fleet/vehicles",
                json={
                    "make_model": f"Maint_{uid()}",
                    "license_plate": f"MP-{uid()[:4]}",
                    "vehicle_type": "van",
                    "status": "active",
                    "mileage": 10000,
                },
                headers=setup.admin_headers,
            )
            vehicle_id = create_r.json()["data"]["id"]
        await call(
            client,
            "fleet",
            "POST",
            "/api/v1/fleet/maintenance",
            headers=setup.admin_headers,
            json={
                "vehicle_id": vehicle_id,
                "maintenance_type": "oil_change",
                "cost": 2500.0,
                "odometer": 10500,
            },
            expected=201,
        )

    async def test_list_maintenance(self, client, setup):
        if TEST.vehicle_id:
            vehicle_id = str(TEST.vehicle_id)
        else:
            create_r = await client.post(
                "/api/v1/fleet/vehicles",
                json={
                    "make_model": f"MaintList_{uid()}",
                    "license_plate": f"CG-{uid()[:4]}",
                    "vehicle_type": "car",
                    "status": "active",
                    "mileage": 25000,
                },
                headers=setup.admin_headers,
            )
            vehicle_id = create_r.json()["data"]["id"]
        await call(
            client,
            "fleet",
            "GET",
            f"/api/v1/fleet/vehicles/{vehicle_id}/maintenance",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_checkout_equipment(self, client, setup):
        r = await call(
            client,
            "fleet",
            "POST",
            "/api/v1/fleet/equipment",
            headers=setup.admin_headers,
            json={
                "equipment_name": f"FirstAid_{uid()}",
                "checked_out_by": str(setup.admin_user_id)
                if hasattr(setup, "admin_user_id") and setup.admin_user_id
                else str(uuid.uuid4()),
            },
            expected=201,
        )
        TEST.equipment_checkout_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_equipment(self, client, setup):
        await call(
            client,
            "fleet",
            "GET",
            "/api/v1/fleet/equipment",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_get_equipment(self, client, setup):
        if TEST.equipment_checkout_id:
            checkout_id = str(TEST.equipment_checkout_id)
        else:
            checkout_id = str(uuid.uuid4())
        await call(
            client,
            "fleet",
            "GET",
            f"/api/v1/fleet/equipment/{checkout_id}",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_return_equipment(self, client, setup):
        if TEST.equipment_checkout_id:
            checkout_id = str(TEST.equipment_checkout_id)
        else:
            checkout_id = str(uuid.uuid4())
        await call(
            client,
            "fleet",
            "POST",
            f"/api/v1/fleet/equipment/{checkout_id}/return",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_bulk_delete_fleet(self, client, setup):
        create_r = await client.post(
            "/api/v1/fleet/vehicles",
            json={
                "make_model": f"BulkDel_{uid()}",
                "license_plate": f"PB-{uid()[:4]}",
                "vehicle_type": "bike",
                "status": "inactive",
                "mileage": 500,
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            vehicle_id = create_r.json()["data"]["id"]
            await call(
                client,
                "fleet",
                "POST",
                "/api/v1/fleet/bulk/delete",
                headers=setup.admin_headers,
                json={
                    "ids": [vehicle_id],
                },
                expected=200,
            )

    async def test_bulk_status_update_fleet(self, client, setup):
        if TEST.vehicle_id:
            vehicle_id = str(TEST.vehicle_id)
        else:
            create_r = await client.post(
                "/api/v1/fleet/vehicles",
                json={
                    "make_model": f"BulkStat_{uid()}",
                    "license_plate": f"HR-{uid()[:4]}",
                    "vehicle_type": "van",
                    "status": "active",
                    "mileage": 4000,
                },
                headers=setup.admin_headers,
            )
            vehicle_id = create_r.json()["data"]["id"]
        await call(
            client,
            "fleet",
            "POST",
            "/api/v1/fleet/bulk/status-update",
            headers=setup.admin_headers,
            json={
                "ids": [vehicle_id],
                "status": "active",
            },
            expected=200,
        )
