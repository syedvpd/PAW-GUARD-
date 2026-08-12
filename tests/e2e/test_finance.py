"""E2E tests for FINANCE module (25 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestFinanceEndpoints:
    """All 25 finance endpoints."""

    # ── Accounts ─────────────────────────────────────────────────────────

    async def test_create_account(self, client, setup):
        r = await call(client, "finance", "POST", "/api/v1/finance/accounts",
                       headers=setup.admin_headers, json={
                           "account_code": f"100{_uid()}",
                           "account_name": f"Cash_{uid()}",
                           "account_type": "asset",
                           "category": "cash",
                           "opening_balance": "10000.00",
                       }, expected=201)
        TEST.finance_account_debit_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_accounts(self, client, setup):
        r = await call(client, "finance", "GET", "/api/v1/finance/accounts",
                       headers=setup.admin_headers, expected=200)

    async def test_get_account(self, client, setup):
        if TEST.finance_account_debit_id:
            account_id = str(TEST.finance_account_debit_id)
        else:
            create_r = await client.post("/api/v1/finance/accounts", json={
                "account_code": f"300{_uid()}",
                "account_name": f"GetAccount_{uid()}",
                "account_type": "asset",
                "category": "cash",
                "opening_balance": "5000.00",
            }, headers=setup.admin_headers)
            account_id = create_r.json()["data"]["id"]
        r = await call(client, "finance", "GET",
                       f"/api/v1/finance/accounts/{account_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_update_account(self, client, setup):
        if TEST.finance_account_debit_id:
            account_id = str(TEST.finance_account_debit_id)
        else:
            create_r = await client.post("/api/v1/finance/accounts", json={
                "account_code": f"400{_uid()}",
                "account_name": f"UpdAccount_{uid()}",
                "account_type": "asset",
                "category": "cash",
                "opening_balance": "2000.00",
            }, headers=setup.admin_headers)
            account_id = create_r.json()["data"]["id"]
        r = await call(client, "finance", "PUT",
                       f"/api/v1/finance/accounts/{account_id}",
                       headers=setup.admin_headers, json={
                           "account_name": "Updated Account",
                       }, expected=200)

    async def test_delete_account(self, client, setup):
        create_r = await client.post("/api/v1/finance/accounts", json={
            "account_code": f"500{_uid()}",
            "account_name": f"DelAccount_{uid()}",
            "account_type": "asset",
            "category": "cash",
            "opening_balance": "0.00",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            account_id = create_r.json()["data"]["id"]
            r = await call(client, "finance", "DELETE",
                           f"/api/v1/finance/accounts/{account_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_bulk_delete_accounts(self, client, setup):
        create_r = await client.post("/api/v1/finance/accounts", json={
            "account_code": f"600{_uid()}",
            "account_name": f"BulkDelAccount_{uid()}",
            "account_type": "asset",
            "category": "cash",
            "opening_balance": "0.00",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            account_id = create_r.json()["data"]["id"]
            r = await call(client, "finance", "POST",
                           "/api/v1/finance/accounts/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [account_id],
                           }, expected=200)

    async def test_account_balances(self, client, setup):
        r = await call(client, "finance", "GET", "/api/v1/finance/account-balances",
                       headers=setup.admin_headers, expected=200)

    # ── Transactions ─────────────────────────────────────────────────────

    async def test_create_transaction(self, client, setup):
        debit_id = str(TEST.finance_account_debit_id) if TEST.finance_account_debit_id else str(uuid.uuid4())
        credit_id = str(TEST.finance_account_credit_id) if TEST.finance_account_credit_id else str(uuid.uuid4())
        r = await call(client, "finance", "POST", "/api/v1/finance/transactions",
                       headers=setup.admin_headers, json={
                           "debit_account_id": debit_id,
                           "credit_account_id": credit_id,
                           "amount": "500.00",
                           "description": "Test transaction",
                       }, expected=201)
        TEST.transaction_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_transactions(self, client, setup):
        r = await call(client, "finance", "GET", "/api/v1/finance/transactions",
                       headers=setup.admin_headers, expected=200)

    async def test_get_transaction(self, client, setup):
        if TEST.transaction_id:
            tx_id = str(TEST.transaction_id)
        else:
            debit_id = str(TEST.finance_account_debit_id) if TEST.finance_account_debit_id else str(uuid.uuid4())
            credit_id = str(TEST.finance_account_credit_id) if TEST.finance_account_credit_id else str(uuid.uuid4())
            create_r = await client.post("/api/v1/finance/transactions", json={
                "debit_account_id": debit_id,
                "credit_account_id": credit_id,
                "amount": "200.00",
                "description": "Get transaction",
            }, headers=setup.admin_headers)
            tx_id = create_r.json()["data"]["id"]
        r = await call(client, "finance", "GET",
                       f"/api/v1/finance/transactions/{tx_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_transaction(self, client, setup):
        debit_id = str(TEST.finance_account_debit_id) if TEST.finance_account_debit_id else str(uuid.uuid4())
        credit_id = str(TEST.finance_account_credit_id) if TEST.finance_account_credit_id else str(uuid.uuid4())
        create_r = await client.post("/api/v1/finance/transactions", json={
            "debit_account_id": debit_id,
            "credit_account_id": credit_id,
            "amount": "100.00",
            "description": "Del transaction",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            tx_id = create_r.json()["data"]["id"]
            r = await call(client, "finance", "DELETE",
                           f"/api/v1/finance/transactions/{tx_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_update_transaction_status(self, client, setup):
        if TEST.transaction_id:
            tx_id = str(TEST.transaction_id)
        else:
            debit_id = str(TEST.finance_account_debit_id) if TEST.finance_account_debit_id else str(uuid.uuid4())
            credit_id = str(TEST.finance_account_credit_id) if TEST.finance_account_credit_id else str(uuid.uuid4())
            create_r = await client.post("/api/v1/finance/transactions", json={
                "debit_account_id": debit_id,
                "credit_account_id": credit_id,
                "amount": "75.00",
                "description": "Status transaction",
            }, headers=setup.admin_headers)
            tx_id = create_r.json()["data"]["id"]
        r = await call(client, "finance", "PATCH",
                       f"/api/v1/finance/transactions/{tx_id}/status",
                       headers=setup.admin_headers, json={
                           "status": "posted",
                       }, expected=200)

    async def test_bulk_delete_transactions(self, client, setup):
        debit_id = str(TEST.finance_account_debit_id) if TEST.finance_account_debit_id else str(uuid.uuid4())
        credit_id = str(TEST.finance_account_credit_id) if TEST.finance_account_credit_id else str(uuid.uuid4())
        create_r = await client.post("/api/v1/finance/transactions", json={
            "debit_account_id": debit_id,
            "credit_account_id": credit_id,
            "amount": "25.00",
            "description": "Bulk del tx",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            tx_id = create_r.json()["data"]["id"]
            r = await call(client, "finance", "POST",
                           "/api/v1/finance/transactions/bulk/delete",
                           headers=setup.admin_headers, json={
                               "ids": [tx_id],
                           }, expected=200)

    # ── Budgets ──────────────────────────────────────────────────────────

    async def test_create_budget(self, client, setup):
        r = await call(client, "finance", "POST", "/api/v1/finance/budgets",
                       headers=setup.admin_headers, json={
                           "name": f"Budget_{uid()}",
                           "amount": "50000.00",
                           "period": "monthly",
                           "start_date": "2026-01-01",
                           "end_date": "2026-01-31",
                       }, expected=201)
        TEST.budget_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_budgets(self, client, setup):
        r = await call(client, "finance", "GET", "/api/v1/finance/budgets",
                       headers=setup.admin_headers, expected=200)

    async def test_get_budget(self, client, setup):
        if TEST.budget_id:
            budget_id = str(TEST.budget_id)
        else:
            create_r = await client.post("/api/v1/finance/budgets", json={
                "name": f"Budget_{uid()}",
                "amount": "30000.00",
                "period": "quarterly",
                "start_date": "2026-01-01",
                "end_date": "2026-03-31",
            }, headers=setup.admin_headers)
            budget_id = create_r.json()["data"]["id"]
        r = await call(client, "finance", "GET",
                       f"/api/v1/finance/budgets/{budget_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_budget(self, client, setup):
        create_r = await client.post("/api/v1/finance/budgets", json={
            "name": f"DelBudget_{uid()}",
            "amount": "10000.00",
            "period": "monthly",
            "start_date": "2026-02-01",
            "end_date": "2026-02-28",
        }, headers=setup.admin_headers)
        if create_r.status_code in (200, 201):
            budget_id = create_r.json()["data"]["id"]
            r = await call(client, "finance", "DELETE",
                           f"/api/v1/finance/budgets/{budget_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_create_budget_item(self, client, setup):
        if TEST.budget_id:
            budget_id = str(TEST.budget_id)
        else:
            create_r = await client.post("/api/v1/finance/budgets", json={
                "name": f"Budget_{uid()}",
                "amount": "20000.00",
                "period": "monthly",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            }, headers=setup.admin_headers)
            budget_id = create_r.json()["data"]["id"]
        r = await call(client, "finance", "POST",
                       f"/api/v1/finance/budgets/{budget_id}/items",
                       headers=setup.admin_headers, json={
                           "category": "food",
                           "budgeted_amount": "5000.00",
                       }, expected=200)

    # ── Recurring ────────────────────────────────────────────────────────

    async def test_create_finance_recurring(self, client, setup):
        r = await call(client, "finance", "POST", "/api/v1/finance/recurring",
                       headers=setup.admin_headers, json={
                           "debit_account_id": str(TEST.finance_account_debit_id) if TEST.finance_account_debit_id else str(uuid.uuid4()),
                           "credit_account_id": str(TEST.finance_account_credit_id) if TEST.finance_account_credit_id else str(uuid.uuid4()),
                           "amount": "1000.00",
                           "description": "Monthly rent",
                           "frequency": "monthly",
                       }, expected=201)
        TEST.recurring_tx_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_finance_recurring(self, client, setup):
        r = await call(client, "finance", "GET", "/api/v1/finance/recurring",
                       headers=setup.admin_headers, expected=200)

    async def test_delete_finance_recurring(self, client, setup):
        if TEST.recurring_tx_id:
            rtx_id = str(TEST.recurring_tx_id)
        else:
            create_r = await client.post("/api/v1/finance/recurring", json={
                "debit_account_id": str(TEST.finance_account_debit_id) if TEST.finance_account_debit_id else str(uuid.uuid4()),
                "credit_account_id": str(TEST.finance_account_credit_id) if TEST.finance_account_credit_id else str(uuid.uuid4()),
                "amount": "500.00",
                "description": "Del recurring",
                "frequency": "weekly",
            }, headers=setup.admin_headers)
            rtx_id = create_r.json()["data"]["id"]
        r = await call(client, "finance", "DELETE",
                       f"/api/v1/finance/recurring/{rtx_id}",
                       headers=setup.admin_headers, expected=200)

    # ── Reports ──────────────────────────────────────────────────────────

    async def test_finance_summary(self, client, setup):
        r = await call(client, "finance", "GET", "/api/v1/finance/summary",
                       headers=setup.admin_headers, expected=200)

    async def test_finance_pnl(self, client, setup):
        r = await call(client, "finance", "GET", "/api/v1/finance/pnl",
                       headers=setup.admin_headers, expected=200)

    async def test_finance_reconcile_summary(self, client, setup):
        r = await call(client, "finance", "GET", "/api/v1/finance/reconcile/summary",
                       headers=setup.admin_headers, expected=200)

    async def test_finance_reconcile_donations(self, client, setup):
        r = await call(client, "finance", "POST", "/api/v1/finance/reconcile/donations",
                       headers=setup.admin_headers, json={
                           "start_date": "2026-01-01",
                           "end_date": "2026-01-31",
                       }, expected=200)
