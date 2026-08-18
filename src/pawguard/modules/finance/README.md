# Finance Module

Double-entry bookkeeping, chart of accounts, transaction management, donation reconciliation, budgets, and P&L reporting.

---

## Architecture

```
finance/
  router.py          # 24 endpoints
  service.py         # FinanceService (GL, reconciliation, budgets)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `ChartOfAccounts` | `chart_of_accounts` | Account hierarchy: type, category, balance |
| `FinancialTransaction` | `financial_transactions` | Transaction record with status lifecycle |
| `GeneralLedgerEntry` | `general_ledger_entries` | Paired debit/credit entries |
| `RecurringTransaction` | `recurring_transactions` | Scheduled recurring entries |
| `Budget` | `budgets` | Budget by fiscal year |
| `BudgetItem` | `budget_items` | Budget allocation per account |

## Account Types

| Type | Categories |
|------|-----------|
| `ASSET` | cash, bank, receivable |
| `LIABILITY` | payable |
| `EQUITY` | — |
| `INCOME` | donation_income, sponsorship_income, adoption_fee |
| `EXPENSE` | medical, shelter, veterinary, supplies, salary, utility, transport |

## Transaction Lifecycle

```
PENDING ──post──> POSTED ──reconcile──> RECONCILED
   │                 │
   └──void──> VOIDED <──void──
```

## Double-Entry Bookkeeping

Every transaction creates **two GL entries** (debit + credit):

```
POST /finance/transactions {debit_account_id, credit_account_id, amount, ...}
  -> Create FinancialTransaction(status=PENDING)
  -> Create GL entry: debit_account DEBIT amount
  -> Create GL entry: credit_account CREDIT amount
```

## Donation Reconciliation

**Auto-posting** (from Donation module):
```
post_donation_to_ledger(donation)
  -> Create RECONCILED transaction (type=RECONCILIATION)
  -> GL: cash_account DEBIT, income_account CREDIT
  -> Idempotent: skips if already reconciled
```

**Bulk reconciliation:**
```
POST /finance/reconcile/donations {donation_ids?}
  -> Find unreconciled successful donations
  -> Create RECONCILED transaction + GL entries for each
  -> Response: {reconciled: count, total_amount: sum}
```

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/finance/accounts` | `finance:create` | Create account |
| GET | `/finance/accounts` | `finance:read` | List accounts |
| GET | `/finance/accounts/{id}` | `finance:read` | Get account |
| PUT | `/finance/accounts/{id}` | `finance:update` | Update account |
| POST | `/finance/transactions` | `finance:create` | Create transaction (double-entry) |
| GET | `/finance/transactions` | `finance:read` | List transactions |
| PATCH | `/finance/transactions/{id}/status` | `finance:update` | Update status |
| GET | `/finance/summary` | `finance:read` | Income vs expenses summary |
| GET | `/finance/pnl` | `finance:read` | P&L by account |
| GET | `/finance/account-balances` | `finance:read` | Account balances |
| POST | `/finance/reconcile/donations` | `finance:create` | Bulk reconcile donations |
| GET | `/finance/reconcile/summary` | `finance:read` | Reconciliation summary |
| POST | `/finance/budgets` | `finance:create` | Create budget |
| GET | `/finance/budgets` | `finance:read` | List budgets |
| POST | `/finance/budgets/{id}/items` | `finance:update` | Add budget item |
| POST | `/finance/recurring` | `finance:create` | Create recurring |
| GET | `/finance/recurring` | `finance:read` | List recurring |
| DELETE | `/finance/recurring/{id}` | `finance:update` | Cancel recurring |

## Finance Summary

```
GET /finance/summary?period_start=&period_end=
  -> Aggregates:
     - Manual INCOME (POSTED/RECONCILED)
     - RECONCILIATION transactions
     - Unreconciled donation income (self-healing)
     - EXPENSE (POSTED/RECONCILED)
  -> Returns: total_income, total_expenses, net_balance
```

## P&L Report

```
GET /finance/pnl?period_start=&period_end=
  -> Joins GL entries with Chart of Accounts
  -> Per-account income and expenses
  -> Returns: income[], expenses[], net_income
```

## Cross-Module Interactions

| Source | Trigger | Effect |
|--------|---------|--------|
| Donation | Successful donation | Auto-post to ledger |
| Donation | Receipt generation | Transaction linked via donation_id |
| Budget | Expense tracking | `total_spent` updated on transactions |
