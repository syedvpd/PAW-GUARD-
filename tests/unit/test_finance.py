"""Unit tests for FinanceService with mocked repository."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.finance.models import (
    Budget,
    ChartOfAccounts,
    FinancialTransaction,
    RecurringTransaction,
    TransactionStatus,
    TransactionType,
)
from pawguard.modules.finance.repository import FinanceRepository
from pawguard.modules.finance.schemas import (
    BudgetCreate,
    ChartOfAccountsCreate,
    ChartOfAccountsUpdate,
    FinancialTransactionCreate,
    RecurringTransactionCreate,
)
from pawguard.modules.finance.service import FinanceService


class TestFinanceService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=FinanceRepository)
        session = AsyncMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        session.execute.return_value = count_result
        repo._session = session
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return FinanceService(mock_repo)

    @pytest.mark.asyncio
    async def test_create_account(self, service, mock_repo):
        mock_repo.get_account_by_code.return_value = None
        payload = ChartOfAccountsCreate(
            account_code="1010",
            account_name="Cash",
            account_type="asset",
            category="cash",
        )
        result = await service.create_account(payload)
        assert result.account_code == "1010"
        mock_repo.create_account.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_account_duplicate_code(self, service, mock_repo):
        mock_repo.get_account_by_code.return_value = ChartOfAccounts(account_code="1010")
        payload = ChartOfAccountsCreate(
            account_code="1010",
            account_name="Cash",
            account_type="asset",
            category="cash",
        )
        with pytest.raises(ConflictError, match="already exists"):
            await service.create_account(payload)

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, service, mock_repo):
        mock_repo.get_account_by_id.return_value = None
        with pytest.raises(NotFoundError, match="Chart of Accounts entry not found"):
            await service.get_account(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_account_found(self, service, mock_repo):
        account_id = uuid.uuid4()
        mock_repo.get_account_by_id.return_value = ChartOfAccounts(
            id=account_id, account_code="1010", account_name="Cash",
        )
        result = await service.get_account(account_id)
        assert result.id == account_id

    @pytest.mark.asyncio
    async def test_update_account(self, service, mock_repo):
        account_id = uuid.uuid4()
        account = ChartOfAccounts(id=account_id, account_code="1010", account_name="Cash")
        mock_repo.get_account_by_id.return_value = account
        payload = ChartOfAccountsUpdate(account_name="Petty Cash")
        result = await service.update_account(account_id, payload)
        assert result.account_name == "Petty Cash"

    @pytest.mark.asyncio
    async def test_update_account_not_found(self, service, mock_repo):
        mock_repo.get_account_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_account(uuid.uuid4(), ChartOfAccountsUpdate())

    @pytest.mark.asyncio
    async def test_list_accounts_paginated(self, service, mock_repo):
        mock_repo.list_accounts_paginated.return_value = ([], 0)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_accounts_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 0

    @pytest.mark.asyncio
    async def test_create_transaction(self, service, mock_repo):
        debit_id = uuid.uuid4()
        credit_id = uuid.uuid4()
        mock_repo.get_account_by_id.side_effect = [
            ChartOfAccounts(id=debit_id, account_code="1010"),
            ChartOfAccounts(id=credit_id, account_code="2020"),
        ]
        payload = FinancialTransactionCreate(
            transaction_type=TransactionType.INCOME,
            transaction_date="2026-07-30",
            amount=1000.00,
            debit_account_id=debit_id,
            credit_account_id=credit_id,
        )
        result = await service.create_transaction(payload)
        assert result.transaction_number.startswith("TXN-")
        mock_repo.create_ledger_entry.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_transaction_debit_not_found(self, service, mock_repo):
        mock_repo.get_account_by_id.return_value = None
        payload = FinancialTransactionCreate(
            transaction_type=TransactionType.INCOME,
            transaction_date="2026-07-30",
            amount=100.00,
            debit_account_id=uuid.uuid4(),
            credit_account_id=uuid.uuid4(),
        )
        with pytest.raises(NotFoundError, match="Debit account not found"):
            await service.create_transaction(payload)

    @pytest.mark.asyncio
    async def test_get_transaction(self, service, mock_repo):
        tx_id = uuid.uuid4()
        mock_repo.get_transaction_by_id.return_value = FinancialTransaction(
            id=tx_id, transaction_number="TXN-001",
        )
        result = await service.get_transaction(tx_id)
        assert result.id == tx_id

    @pytest.mark.asyncio
    async def test_get_transaction_not_found(self, service, mock_repo):
        mock_repo.get_transaction_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_transaction(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_transaction_status(self, service, mock_repo):
        tx_id = uuid.uuid4()
        mock_repo.get_transaction_by_id.return_value = FinancialTransaction(
            id=tx_id, transaction_number="TXN-001", status=TransactionStatus.PENDING,
        )
        result = await service.update_transaction_status(tx_id, TransactionStatus.POSTED)
        assert result.status == TransactionStatus.POSTED

    @pytest.mark.asyncio
    async def test_update_transaction_status_not_found(self, service, mock_repo):
        mock_repo.get_transaction_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_transaction_status(uuid.uuid4(), TransactionStatus.POSTED)

    @pytest.mark.asyncio
    async def test_list_transactions_paginated(self, service, mock_repo):
        mock_repo.list_transactions_paginated.return_value = ([], 0)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_transactions_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 0

    @pytest.mark.asyncio
    async def test_get_finance_summary(self, service, mock_repo):
        mock_repo.get_finance_summary.return_value = {"total_income": 1000}
        result = await service.get_finance_summary("2026-01-01", "2026-12-31")
        assert result["total_income"] == 1000

    @pytest.mark.asyncio
    async def test_get_pnl(self, service, mock_repo):
        mock_repo.get_pnl.return_value = {"net_income": 500}
        result = await service.get_pnl("2026-01-01", "2026-12-31")
        assert result["net_income"] == 500

    @pytest.mark.asyncio
    async def test_get_account_balances(self, service, mock_repo):
        mock_repo.get_account_balances.return_value = []
        result = await service.get_account_balances()
        assert result == []

    @pytest.mark.asyncio
    async def test_soft_delete_account(self, service, mock_repo):
        account_id = uuid.uuid4()
        mock_repo.get_account_by_id.return_value = ChartOfAccounts(
            id=account_id, account_code="1010", account_name="Cash",
        )
        await service.soft_delete_account(account_id)
        assert mock_repo.get_account_by_id.await_count >= 1

    @pytest.mark.asyncio
    async def test_soft_delete_account_not_found(self, service, mock_repo):
        mock_repo.get_account_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_account(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_soft_delete_transaction(self, service, mock_repo):
        tx_id = uuid.uuid4()
        mock_repo.get_transaction_by_id.return_value = FinancialTransaction(
            id=tx_id, transaction_number="TXN-001",
        )
        await service.soft_delete_transaction(tx_id)
        assert mock_repo.get_transaction_by_id.await_count >= 1

    @pytest.mark.asyncio
    async def test_soft_delete_transaction_not_found(self, service, mock_repo):
        mock_repo.get_transaction_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_transaction(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_budget(self, service, mock_repo):
        payload = BudgetCreate(
            name="Annual 2026",
            fiscal_year=2026,
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        result = await service.create_budget(payload)
        assert result.name == "Annual 2026"
        mock_repo.create_budget.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_budget(self, service, mock_repo):
        budget_id = uuid.uuid4()
        mock_repo.get_budget_by_id.return_value = Budget(id=budget_id, name="Budget")
        result = await service.get_budget(budget_id)
        assert result.id == budget_id

    @pytest.mark.asyncio
    async def test_get_budget_not_found(self, service, mock_repo):
        mock_repo.get_budget_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_budget(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_add_budget_item(self, service, mock_repo):
        budget_id = uuid.uuid4()
        mock_repo.get_budget_by_id.return_value = Budget(id=budget_id, name="Budget", items=[])
        mock_repo.get_account_by_id.return_value = ChartOfAccounts(
            id=uuid.uuid4(), account_code="1010",
        )
        payload = type("Payload", (), {"account_id": uuid.uuid4(), "allocated_amount": 5000})()
        result = await service.add_budget_item(budget_id, payload)
        assert result.id == budget_id

    @pytest.mark.asyncio
    async def test_add_budget_item_budget_not_found(self, service, mock_repo):
        mock_repo.get_budget_by_id.return_value = None
        payload = type("Payload", (), {"account_id": uuid.uuid4(), "allocated_amount": 5000})()
        with pytest.raises(NotFoundError, match="Budget not found"):
            await service.add_budget_item(uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_list_budgets_paginated(self, service, mock_repo):
        mock_repo.list_budgets_paginated.return_value = ([], 0)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_budgets_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)

    @pytest.mark.asyncio
    async def test_create_recurring(self, service, mock_repo):
        mock_repo.get_account_by_id.side_effect = [
            ChartOfAccounts(id=uuid.uuid4(), account_code="1010"),
            ChartOfAccounts(id=uuid.uuid4(), account_code="2020"),
        ]
        payload = RecurringTransactionCreate(
            name="Monthly Rent",
            transaction_type=TransactionType.EXPENSE,
            amount=2000.00,
            interval="monthly",
            start_date="2026-01-01",
            debit_account_id=uuid.uuid4(),
            credit_account_id=uuid.uuid4(),
        )
        result = await service.create_recurring(payload)
        assert result.name == "Monthly Rent"

    @pytest.mark.asyncio
    async def test_create_recurring_debit_not_found(self, service, mock_repo):
        mock_repo.get_account_by_id.return_value = None
        payload = RecurringTransactionCreate(
            name="Test",
            transaction_type=TransactionType.EXPENSE,
            amount=100.00,
            interval="monthly",
            start_date="2026-01-01",
            debit_account_id=uuid.uuid4(),
            credit_account_id=uuid.uuid4(),
        )
        with pytest.raises(NotFoundError, match="Debit account not found"):
            await service.create_recurring(payload)

    @pytest.mark.asyncio
    async def test_list_recurring_paginated(self, service, mock_repo):
        mock_repo.list_recurring_paginated.return_value = ([], 0)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_recurring_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)

    @pytest.mark.asyncio
    async def test_soft_delete_budget(self, service, mock_repo):
        budget_id = uuid.uuid4()
        mock_repo.get_budget_by_id.return_value = Budget(id=budget_id, name="Budget")
        await service.soft_delete_budget(budget_id)
        mock_repo.get_budget_by_id.assert_awaited_once_with(budget_id)

    @pytest.mark.asyncio
    async def test_soft_delete_budget_not_found(self, service, mock_repo):
        mock_repo.get_budget_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_budget(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_soft_delete_recurring(self, service, mock_repo):
        rtx_id = uuid.uuid4()
        mock_repo.get_recurring_by_id.return_value = RecurringTransaction(
            id=rtx_id, name="Rent",
        )
        await service.soft_delete_recurring(rtx_id)

    @pytest.mark.asyncio
    async def test_soft_delete_recurring_not_found(self, service, mock_repo):
        mock_repo.get_recurring_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_recurring(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_bulk_delete_accounts(self, service, mock_repo):
        aid = uuid.uuid4()
        mock_repo.get_account_by_id.return_value = ChartOfAccounts(
            id=aid, account_code="1010", account_name="Cash",
        )
        count = await service.bulk_delete_accounts([aid])
        assert count == 1

    @pytest.mark.asyncio
    async def test_bulk_delete_transactions(self, service, mock_repo):
        tid = uuid.uuid4()
        mock_repo.get_transaction_by_id.return_value = FinancialTransaction(
            id=tid, transaction_number="TXN-001",
        )
        count = await service.bulk_delete_transactions([tid])
        assert count == 1

    @pytest.mark.asyncio
    async def test_reconcile_donations(self, service, mock_repo):
        mock_repo.get_unreconciled_donations.return_value = []
        result = await service.reconcile_donations()
        assert result["reconciled"] == 0

    @pytest.mark.asyncio
    async def test_get_donation_reconciliation_summary(self, service, mock_repo):
        mock_repo.get_donation_reconciliation_summary.return_value = {"total_donations": 5}
        result = await service.get_donation_reconciliation_summary()
        assert result["total_donations"] == 5
