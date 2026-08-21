"""E2E tests for INVENTORY module (12 endpoints)."""

import uuid

import pytest
from tests.e2e.factories import TEST
from tests.e2e.helpers import call, uid


@pytest.mark.asyncio
class TestInventoryEndpoints:
    """All 12 inventory endpoints."""

    async def test_create_inventory_item(self, client, setup):
        r = await call(
            client,
            "inventory",
            "POST",
            "/api/v1/inventory/items",
            headers=setup.admin_headers,
            json={
                "name": f"Item_{uid()}",
                "category": "food",
                "quantity": 100.0,
                "unit": "kg",
                "reorder_threshold": 10.0,
                "unit_cost": 5.0,
            },
            expected=201,
        )
        TEST.inventory_item_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_inventory_items(self, client, setup):
        await call(
            client,
            "inventory",
            "GET",
            "/api/v1/inventory/items",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_get_inventory_item(self, client, setup):
        if TEST.inventory_item_id:
            item_id = str(TEST.inventory_item_id)
        else:
            create_r = await client.post(
                "/api/v1/inventory/items",
                json={
                    "name": f"Item_{uid()}",
                    "category": "medicine",
                    "quantity": 50.0,
                    "unit": "pieces",
                    "reorder_threshold": 5.0,
                    "unit_cost": 10.0,
                },
                headers=setup.admin_headers,
            )
            item_id = create_r.json()["data"]["id"]
        await call(
            client,
            "inventory",
            "GET",
            f"/api/v1/inventory/items/{item_id}",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_delete_inventory_item(self, client, setup):
        create_r = await client.post(
            "/api/v1/inventory/items",
            json={
                "name": f"DelItem_{uid()}",
                "category": "cleaning",
                "quantity": 20.0,
                "unit": "liters",
                "reorder_threshold": 2.0,
                "unit_cost": 15.0,
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            item_id = create_r.json()["data"]["id"]
            await call(
                client,
                "inventory",
                "DELETE",
                f"/api/v1/inventory/items/{item_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_admin_delete_inventory_item(self, client, setup):
        create_r = await client.post(
            "/api/v1/inventory/items",
            json={
                "name": f"AdminDel_{uid()}",
                "category": "food",
                "quantity": 30.0,
                "unit": "kg",
                "reorder_threshold": 5.0,
                "unit_cost": 8.0,
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            item_id = create_r.json()["data"]["id"]
            await call(
                client,
                "inventory",
                "DELETE",
                f"/api/v1/inventory/admin/inventory/items/{item_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_bulk_delete_inventory(self, client, setup):
        create_r = await client.post(
            "/api/v1/inventory/items",
            json={
                "name": f"BulkItem_{uid()}",
                "category": "supplies",
                "quantity": 40.0,
                "unit": "pieces",
                "reorder_threshold": 8.0,
                "unit_cost": 3.0,
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            item_id = create_r.json()["data"]["id"]
            await call(
                client,
                "inventory",
                "POST",
                "/api/v1/inventory/items/bulk/delete",
                headers=setup.admin_headers,
                json={
                    "ids": [item_id],
                },
                expected=200,
            )

    async def test_create_movement(self, client, setup):
        if TEST.inventory_item_id:
            item_id = str(TEST.inventory_item_id)
        else:
            create_r = await client.post(
                "/api/v1/inventory/items",
                json={
                    "name": f"MovItem_{uid()}",
                    "category": "food",
                    "quantity": 80.0,
                    "unit": "kg",
                    "reorder_threshold": 10.0,
                    "unit_cost": 6.0,
                },
                headers=setup.admin_headers,
            )
            item_id = create_r.json()["data"]["id"]
        await call(
            client,
            "inventory",
            "POST",
            "/api/v1/inventory/movements",
            headers=setup.admin_headers,
            json={
                "item_id": item_id,
                "movement_type": "out",
                "quantity": 5.0,
                "notes": "Feeding dogs",
            },
            expected=201,
        )

    async def test_list_item_movements(self, client, setup):
        if TEST.inventory_item_id:
            item_id = str(TEST.inventory_item_id)
        else:
            create_r = await client.post(
                "/api/v1/inventory/items",
                json={
                    "name": f"MovListItem_{uid()}",
                    "category": "medicine",
                    "quantity": 25.0,
                    "unit": "tablets",
                    "reorder_threshold": 5.0,
                    "unit_cost": 2.0,
                },
                headers=setup.admin_headers,
            )
            item_id = create_r.json()["data"]["id"]
        await call(
            client,
            "inventory",
            "GET",
            f"/api/v1/inventory/items/{item_id}/movements",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_create_requisition(self, client, setup):
        if TEST.inventory_item_id:
            item_id = str(TEST.inventory_item_id)
        else:
            create_r = await client.post(
                "/api/v1/inventory/items",
                json={
                    "name": f"ReqItem_{uid()}",
                    "category": "food",
                    "quantity": 60.0,
                    "unit": "kg",
                    "reorder_threshold": 10.0,
                    "unit_cost": 4.0,
                },
                headers=setup.admin_headers,
            )
            item_id = create_r.json()["data"]["id"]
        r = await call(
            client,
            "inventory",
            "POST",
            "/api/v1/inventory/requisitions",
            headers=setup.admin_headers,
            json={
                "item_id": item_id,
                "quantity": 20.0,
                "reason": "Low stock",
            },
            expected=201,
        )
        TEST.requisition_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_requisitions(self, client, setup):
        await call(
            client,
            "inventory",
            "GET",
            "/api/v1/inventory/requisitions",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_requisition_status(self, client, setup):
        if TEST.requisition_id:
            req_id = str(TEST.requisition_id)
        else:
            create_r = await client.post(
                "/api/v1/inventory/requisitions",
                json={
                    "item_id": str(TEST.inventory_item_id)
                    if TEST.inventory_item_id
                    else str(uuid.uuid4()),
                    "quantity": 10.0,
                    "reason": "Urgent",
                },
                headers=setup.admin_headers,
            )
            req_id = create_r.json()["data"]["id"]
        await call(
            client,
            "inventory",
            "PUT",
            f"/api/v1/inventory/requisitions/{req_id}/status",
            headers=setup.admin_headers,
            json={
                "status": "approved",
            },
            expected=200,
        )

    async def test_bulk_status_requisitions(self, client, setup):
        if TEST.requisition_id:
            req_id = str(TEST.requisition_id)
        else:
            create_r = await client.post(
                "/api/v1/inventory/requisitions",
                json={
                    "item_id": str(TEST.inventory_item_id)
                    if TEST.inventory_item_id
                    else str(uuid.uuid4()),
                    "quantity": 5.0,
                    "reason": "Bulk status",
                },
                headers=setup.admin_headers,
            )
            req_id = create_r.json()["data"]["id"]
        await call(
            client,
            "inventory",
            "POST",
            "/api/v1/inventory/requisitions/bulk/status",
            headers=setup.admin_headers,
            json={
                "ids": [req_id],
                "status": "fulfilled",
            },
            expected=200,
        )
