import uuid
from datetime import UTC, date, datetime
from typing import Any

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.finance.models import (
    AccountCategory,
    AccountType,
    Budget,
    BudgetItem,
    ChartOfAccounts,
    FinancialTransaction,
    GeneralLedgerEntry,
    RecurringTransaction,
    TransactionStatus,
    TransactionType,
)
from pawguard.modules.finance.repository import FinanceRepository
from pawguard.modules.finance.schemas import (
    AccountBalanceResponse,
    BudgetCreate,
    BudgetItemCreate,
    BudgetResponse,
    ChartOfAccountsCreate,
    ChartOfAccountsResponse,
    ChartOfAccountsUpdate,
    FinancialTransactionCreate,
    FinancialTransactionResponse,
    RecurringTransactionCreate,
    RecurringTransactionResponse,
)
from pawguard.services.audit_service import AuditService


class FinanceService:
    def __init__(
        self,
        repository: FinanceRepository,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._audit = audit_service

    async def create_account(
        self,
        payload: ChartOfAccountsCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ChartOfAccounts:
        existing = await self._repo.get_account_by_code(payload.account_code)
        if existing:
            raise ConflictError(
                f"Account code '{payload.account_code}' already exists."
            )
        account = ChartOfAccounts(
            account_code=payload.account_code,
            account_name=payload.account_name,
            account_type=payload.account_type,
            category=payload.category,
            description=payload.description,
            parent_account_id=payload.parent_account_id,
            opening_balance=payload.opening_balance,
            current_balance=payload.opening_balance,
        )
        await self._repo.create_account(account)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_ACCOUNT_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "account_id": str(account.id),
                    "account_code": payload.account_code,
                },
            )
        return account

    async def get_account(self, account_id: uuid.UUID) -> ChartOfAccounts:
        account = await self._repo.get_account_by_id(account_id)
        if not account:
            raise NotFoundError("Chart of Accounts entry not found.")
        return account

    async def update_account(
        self,
        account_id: uuid.UUID,
        payload: ChartOfAccountsUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> ChartOfAccounts:
        account = await self._repo.get_account_by_id(account_id)
        if not account:
            raise NotFoundError("Chart of Accounts entry not found.")
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
        for key, value in update_data.items():
            setattr(account, key, value)
        await self._repo._session.flush()
        await self._repo._session.refresh(account)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_ACCOUNT_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "account_id": str(account_id),
                    "changes": update_data,
                },
            )
        return account

    async def list_accounts_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        account_type: AccountType | None = None,
        category: AccountCategory | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResponse[ChartOfAccountsResponse]:
        results, total = await self._repo.list_accounts_paginated(
            page, sort, search_term, account_type, category, is_active
        )
        return PaginatedResponse(
            data=[ChartOfAccountsResponse.model_validate(a) for a in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def create_transaction(
        self,
        payload: FinancialTransactionCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FinancialTransaction:
        debit_account = await self._repo.get_account_by_id(
            payload.debit_account_id
        )
        if not debit_account:
            raise NotFoundError("Debit account not found.")
        credit_account = await self._repo.get_account_by_id(
            payload.credit_account_id
        )
        if not credit_account:
            raise NotFoundError("Credit account not found.")
        tx_count = await self._repo._session.execute(
            __import__('sqlalchemy').select(
                __import__('sqlalchemy').func.count(FinancialTransaction.id)
            )
        )
        count = tx_count.scalar_one() + 1
        tx_number = (
            f"TXN-{datetime.now(UTC).strftime('%Y%m%d')}-{count:05d}"
        )
        tx = FinancialTransaction(
            transaction_number=tx_number,
            transaction_type=payload.transaction_type,
            transaction_date=payload.transaction_date,
            amount=payload.amount,
            currency=payload.currency,
            description=payload.description,
            reference_type=payload.reference_type,
            reference_id=payload.reference_id,
            donation_id=payload.donation_id,
            status=TransactionStatus.PENDING,
        )
        await self._repo.create_transaction(tx)
        if payload.transaction_type in (
            TransactionType.INCOME,
            TransactionType.RECONCILIATION,
        ) or payload.transaction_type == TransactionType.EXPENSE:
            debit, credit = payload.debit_account_id, payload.credit_account_id
            debit_amt, credit_amt = payload.amount, payload.amount
        else:
            debit, credit = payload.debit_account_id, payload.credit_account_id
            debit_amt, credit_amt = payload.amount, payload.amount
        entry = GeneralLedgerEntry(
            account_id=debit,
            transaction_id=tx.id,
            debit_amount=debit_amt,
            credit_amount=0,
            entry_date=payload.transaction_date,
            description=payload.description,
        )
        await self._repo.create_ledger_entry(entry)
        entry2 = GeneralLedgerEntry(
            account_id=credit,
            transaction_id=tx.id,
            debit_amount=0,
            credit_amount=credit_amt,
            entry_date=payload.transaction_date,
            description=payload.description,
        )
        await self._repo.create_ledger_entry(entry2)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "tx_id": str(tx.id),
                    "tx_number": tx_number,
                    "amount": str(payload.amount),
                },
            )
        return tx

    async def get_transaction(
        self, tx_id: uuid.UUID
    ) -> FinancialTransaction:
        tx = await self._repo.get_transaction_by_id(tx_id)
        if not tx:
            raise NotFoundError("Transaction not found.")
        return tx

    async def update_transaction_status(
        self,
        tx_id: uuid.UUID,
        status: TransactionStatus,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FinancialTransaction:
        tx = await self._repo.get_transaction_by_id(tx_id)
        if not tx:
            raise NotFoundError("Transaction not found.")
        tx.status = status
        if status == TransactionStatus.RECONCILED:
            tx.reconciled_at = datetime.now(UTC)
        await self._repo._session.flush()
        await self._repo._session.refresh(tx)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"tx_id": str(tx_id), "status": status.value},
            )
        return tx

    async def list_transactions_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        transaction_type: TransactionType | None = None,
        status: TransactionStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PaginatedResponse[FinancialTransactionResponse]:
        results, total = await self._repo.list_transactions_paginated(
            page, sort, search_term, transaction_type, status, date_from, date_to
        )
        return PaginatedResponse(
            data=[
                FinancialTransactionResponse.model_validate(t)
                for t in results
            ],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def get_finance_summary(
        self, period_start: date, period_end: date
    ) -> dict[str, Any]:
        return await self._repo.get_finance_summary(period_start, period_end)

    async def get_pnl(
        self, period_start: date, period_end: date
    ) -> dict[str, Any]:
        return await self._repo.get_pnl(period_start, period_end)

    async def reconcile_donations(
        self,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        unreconciled = await self._repo.get_unreconciled_donations()
        count = 0
        for donation in unreconciled:
            tx_count = await self._repo._session.execute(
                __import__('sqlalchemy').select(
                    __import__('sqlalchemy').func.count(FinancialTransaction.id)
                )
            )
            c = tx_count.scalar_one() + 1
            tx = FinancialTransaction(
                transaction_number=(
                    f"DR-{datetime.now(UTC).strftime('%Y%m%d')}-{c:05d}"
                ),
                transaction_type=TransactionType.RECONCILIATION,
                transaction_date=datetime.now(UTC).date(),
                amount=donation.amount,
                currency="USD",
                description=f"Donation reconciliation - {donation.id}",
                donation_id=donation.id,
                status=TransactionStatus.RECONCILED,
                reconciled_at=datetime.now(UTC),
            )
            await self._repo.create_transaction(tx)
            income_accounts = await self._repo._session.execute(
                __import__('sqlalchemy').select(ChartOfAccounts).where(
                    ChartOfAccounts.account_type == AccountType.INCOME,
                    ChartOfAccounts.category == AccountCategory.DONATION_INCOME,
                    ChartOfAccounts.deleted_at.is_(None),
                ).limit(1)
            )
            income_account = income_accounts.scalar_one_or_none()
            cash_accounts = await self._repo._session.execute(
                __import__('sqlalchemy').select(ChartOfAccounts).where(
                    ChartOfAccounts.account_type == AccountType.ASSET,
                    ChartOfAccounts.category.in_(
                        [AccountCategory.CASH, AccountCategory.BANK]
                    ),
                    ChartOfAccounts.deleted_at.is_(None),
                ).limit(1)
            )
            cash_account = cash_accounts.scalar_one_or_none()
            if income_account and cash_account:
                entry1 = GeneralLedgerEntry(
                    account_id=cash_account.id,
                    transaction_id=tx.id,
                    debit_amount=donation.amount,
                    credit_amount=0,
                    entry_date=datetime.now(UTC).date(),
                    description=(
                        f"Donation {donation.id} reconciliation"
                    ),
                )
                await self._repo.create_ledger_entry(entry1)
                entry2 = GeneralLedgerEntry(
                    account_id=income_account.id,
                    transaction_id=tx.id,
                    debit_amount=0,
                    credit_amount=donation.amount,
                    entry_date=datetime.now(UTC).date(),
                    description=(
                        f"Donation {donation.id} reconciliation"
                    ),
                )
                await self._repo.create_ledger_entry(entry2)
            count += 1
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_DONATIONS_RECONCILED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"count": count},
            )
        return {
            "reconciled": count,
            "total_amount": sum(d.amount for d in unreconciled),
        }

    async def get_donation_reconciliation_summary(self) -> dict[str, Any]:
        return await self._repo.get_donation_reconciliation_summary()

    async def get_account_balances(self) -> list[AccountBalanceResponse]:
        accounts = await self._repo.get_account_balances()
        return [AccountBalanceResponse.model_validate(a) for a in accounts]

    async def soft_delete_account(
        self,
        account_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        account = await self._repo.get_account_by_id(account_id)
        if not account:
            raise NotFoundError("Account not found.")
        account.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_ACCOUNT_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"account_id": str(account_id)},
            )

    async def soft_delete_transaction(
        self,
        tx_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        tx = await self._repo.get_transaction_by_id(tx_id)
        if not tx:
            raise NotFoundError("Transaction not found.")
        tx.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"tx_id": str(tx_id)},
            )

    async def create_budget(
        self,
        payload: BudgetCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Budget:
        budget = Budget(
            name=payload.name,
            fiscal_year=payload.fiscal_year,
            start_date=payload.start_date,
            end_date=payload.end_date,
            notes=payload.notes,
            total_budget=0,
            total_spent=0,
        )
        await self._repo.create_budget(budget)
        saved_budget = await self._repo.get_budget_by_id(budget.id)
        if not saved_budget:
            raise NotFoundError("Budget not found.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_BUDGET_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"budget_id": str(saved_budget.id)},
            )
        return saved_budget

    async def get_budget(self, budget_id: uuid.UUID) -> Budget:
        budget = await self._repo.get_budget_by_id(budget_id)
        if not budget:
            raise NotFoundError("Budget not found.")
        return budget

    async def add_budget_item(
        self,
        budget_id: uuid.UUID,
        payload: BudgetItemCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Budget:
        budget = await self._repo.get_budget_by_id(budget_id)
        if not budget:
            raise NotFoundError("Budget not found.")
        account = await self._repo.get_account_by_id(payload.account_id)
        if not account:
            raise NotFoundError("Account not found.")
        item = BudgetItem(
            budget_id=budget_id,
            account_id=payload.account_id,
            allocated_amount=payload.allocated_amount,
        )
        await self._repo.create_budget_item(item)
        budget.total_budget = (
            sum(i.allocated_amount for i in budget.items)
            + payload.allocated_amount
        )
        await self._repo._session.flush()
        saved_budget = await self._repo.get_budget_by_id(budget_id)
        if not saved_budget:
            raise NotFoundError("Budget not found.")
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_BUDGET_ITEM_ADDED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "budget_id": str(budget_id),
                    "account_id": str(payload.account_id),
                },
            )
        return saved_budget

    async def list_budgets_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        fiscal_year: int | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResponse[BudgetResponse]:
        results, total = await self._repo.list_budgets_paginated(
            page, sort, search_term, fiscal_year, is_active
        )
        return PaginatedResponse(
            data=[BudgetResponse.model_validate(b) for b in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def create_recurring(
        self,
        payload: RecurringTransactionCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RecurringTransaction:
        debit = await self._repo.get_account_by_id(payload.debit_account_id)
        if not debit:
            raise NotFoundError("Debit account not found.")
        credit = await self._repo.get_account_by_id(
            payload.credit_account_id
        )
        if not credit:
            raise NotFoundError("Credit account not found.")
        rtx = RecurringTransaction(**payload.model_dump())
        await self._repo.create_recurring(rtx)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_RECURRING_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"recurring_id": str(rtx.id)},
            )
        return rtx

    async def list_recurring_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResponse[RecurringTransactionResponse]:
        results, total = await self._repo.list_recurring_paginated(
            page, sort, search_term, is_active
        )
        return PaginatedResponse(
            data=[
                RecurringTransactionResponse.model_validate(r)
                for r in results
            ],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def soft_delete_budget(
        self,
        budget_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        budget = await self._repo.get_budget_by_id(budget_id)
        if not budget:
            raise NotFoundError("Budget not found.")
        budget.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()

    async def soft_delete_recurring(
        self,
        rtx_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        rtx = await self._repo.get_recurring_by_id(rtx_id)
        if not rtx:
            raise NotFoundError("Recurring transaction not found.")
        rtx.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()

    async def bulk_delete_accounts(
        self,
        ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = 0
        for aid in ids:
            acct = await self._repo.get_account_by_id(aid)
            if acct:
                acct.deleted_at = datetime.now(UTC)
                count += 1
        await self._repo._session.flush()
        return count

    async def bulk_delete_transactions(
        self,
        ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = 0
        for tid in ids:
            tx = await self._repo.get_transaction_by_id(tid)
            if tx:
                tx.deleted_at = datetime.now(UTC)
                count += 1
        await self._repo._session.flush()
        return count
