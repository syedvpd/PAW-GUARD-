import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from pawguard.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationFailedError,
)
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.donation.models import Donation, DonationStatus
from pawguard.modules.finance.models import (
    AccountCategory,
    AccountType,
    Budget,
    BudgetItem,
    ChartOfAccounts,
    ExpenseCategory,
    ExpenseStatus,
    FinanceExpense,
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
    FinanceExpenseCreate,
    FinanceExpenseResponse,
    FinanceExpenseUpdate,
    FinancialTransactionCreate,
    FinancialTransactionResponse,
    RecurringTransactionCreate,
    RecurringTransactionResponse,
    RefundResponse,
    TaxReceipt80GResponse,
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
        sequence = await self._repo.next_transaction_sequence()
        tx_number = (
            f"TXN-{datetime.now(UTC).strftime('%Y%m%d')}-{sequence:05d}"
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
        old_status = tx.status
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
                # Structured before/after snapshots (audit finding #3).
                before_state={"status": TransactionStatus(old_status).value},
                after_state={"status": status.value},
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

    async def post_donation_to_ledger(
        self,
        donation: Donation,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> bool:
        """Auto-post a successful donation into the finance ledger.

        Idempotent: skips donations that are not SUCCESS or that already have
        a reconciled ledger transaction, so repeated calls never double-book.
        Returns True when a ledger transaction was created.
        """
        if donation.status != DonationStatus.SUCCESS:
            return False
        if await self._repo.is_donation_reconciled(donation.id):
            return False
        income_account, cash_account = await self._get_reconcile_accounts()
        await self._reconcile_one_donation(
            donation, income_account=income_account, cash_account=cash_account
        )
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_DONATIONS_RECONCILED,
                actor_id=actor_id,
                ip_address="",
                user_agent="",
                metadata={
                    "donation_id": str(donation.id),
                    "count": 1,
                    "source": "auto",
                },
            )
        return True

    async def reconcile_donations(
        self,
        *,
        donation_ids: list[uuid.UUID] | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        if donation_ids:
            unreconciled: Sequence[Donation] = []
            seen: set[uuid.UUID] = set()
            for donation_id in donation_ids:
                if donation_id in seen:
                    continue
                seen.add(donation_id)
                donation = await self._repo.get_donation_by_id(donation_id)
                if donation is None:
                    raise NotFoundError(
                        f"Donation record not found for id: {donation_id}."
                    )
                if donation.status != DonationStatus.SUCCESS:
                    raise ValidationFailedError(
                        "Only successful donations can be reconciled."
                    )
                if await self._repo.is_donation_reconciled(donation_id):
                    raise ConflictError(
                        f"Donation {donation_id} is already reconciled."
                    )
                unreconciled.append(donation)
        else:
            unreconciled = await self._repo.get_unreconciled_donations()

        income_account, cash_account = await self._get_reconcile_accounts()

        if not unreconciled:
            return {"reconciled": 0, "total_amount": 0}

        # Batch: pre-fetch sequence numbers and build all entities in one transaction
        sequences = []
        for _ in unreconciled:
            seq = await self._repo.next_transaction_sequence()
            sequences.append(seq)

        # Build all transaction + ledger entries
        for i, donation in enumerate(unreconciled):
            seq = sequences[i]
            tx = FinancialTransaction(
                transaction_number=(
                    f"DR-{datetime.now(UTC).strftime('%Y%m%d')}-{seq:05d}"
                ),
                transaction_type=TransactionType.RECONCILIATION,
                transaction_date=datetime.now(UTC).date(),
                amount=donation.amount,
                currency=donation.currency or "USD",
                description=f"Donation reconciliation - {donation.id}",
                donation_id=donation.id,
                status=TransactionStatus.RECONCILED,
                reconciled_at=datetime.now(UTC),
            )
            await self._repo.create_transaction(tx)

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

        await self._repo._session.flush()

        count = len(unreconciled)
        total_amount = sum(d.amount for d in unreconciled)

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_DONATIONS_RECONCILED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"count": count, "total_amount": str(total_amount)},
            )
        return {"reconciled": count, "total_amount": total_amount}

    async def reconcile_donation(
        self,
        donation_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Reconcile a single successful donation into the finance ledger.

        Idempotent guard: a donation that already has a RECONCILED
        transaction is rejected with a conflict rather than double-booked.
        """
        donation = await self._repo.get_donation_by_id(donation_id)
        if donation is None:
            raise NotFoundError("Donation record not found.")
        if donation.status != DonationStatus.SUCCESS:
            raise ValidationFailedError(
                "Only successful donations can be reconciled."
            )
        if await self._repo.is_donation_reconciled(donation_id):
            raise ConflictError("Donation is already reconciled.")

        income_account, cash_account = await self._get_reconcile_accounts()
        await self._reconcile_one_donation(
            donation, income_account=income_account, cash_account=cash_account
        )

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_DONATIONS_RECONCILED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"donation_id": str(donation_id), "count": 1},
            )
        return {"reconciled": 1, "total_amount": float(donation.amount)}

    async def _get_reconcile_accounts(
        self,
    ) -> tuple[ChartOfAccounts | None, ChartOfAccounts | None]:
        income_account = (
            await self._repo._session.execute(
                sa.select(ChartOfAccounts).where(
                    ChartOfAccounts.account_type == AccountType.INCOME,
                    ChartOfAccounts.category == AccountCategory.DONATION_INCOME,
                    ChartOfAccounts.deleted_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        cash_account = (
            await self._repo._session.execute(
                sa.select(ChartOfAccounts).where(
                    ChartOfAccounts.account_type == AccountType.ASSET,
                    ChartOfAccounts.category.in_([AccountCategory.CASH, AccountCategory.BANK]),
                    ChartOfAccounts.deleted_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        return income_account, cash_account

    async def _reconcile_one_donation(
        self,
        donation: Donation,
        *,
        income_account: ChartOfAccounts | None,
        cash_account: ChartOfAccounts | None,
    ) -> None:
        """Create the RECONCILED transaction + GL entries for one donation.
        Shared by the bulk and single-donation reconcile flows."""
        sequence = await self._repo.next_transaction_sequence()
        tx = FinancialTransaction(
            transaction_number=(
                f"DR-{datetime.now(UTC).strftime('%Y%m%d')}-{sequence:05d}"
            ),
            transaction_type=TransactionType.RECONCILIATION,
            transaction_date=datetime.now(UTC).date(),
            amount=donation.amount,
            currency=donation.currency or "USD",
            description=f"Donation reconciliation - {donation.id}",
            donation_id=donation.id,
            status=TransactionStatus.RECONCILED,
            reconciled_at=datetime.now(UTC),
        )
        await self._repo.create_transaction(tx)
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
        count = await self._repo.bulk_soft_delete(ChartOfAccounts, ids)
        await self._repo._session.flush()
        return count

    async def bulk_delete_transactions(
        self,
        ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        count = await self._repo.bulk_soft_delete(FinancialTransaction, ids)
        await self._repo._session.flush()
        return count

    async def create_expense(
        self,
        payload: FinanceExpenseCreate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FinanceExpense:
        if payload.account_id:
            account = await self._repo.get_account_by_id(payload.account_id)
            if not account:
                raise NotFoundError("Account not found.")
        sequence = await self._repo.next_expense_sequence()
        expense_number = f"EXP-{datetime.now(UTC).strftime('%Y%m%d')}-{sequence:05d}"
        expense = FinanceExpense(
            expense_number=expense_number,
            title=payload.title,
            description=payload.description,
            amount=payload.amount,
            currency=payload.currency,
            category=payload.category,
            vendor_name=payload.vendor_name,
            vendor_contact=payload.vendor_contact,
            vendor_gstin=payload.vendor_gstin,
            expense_date=payload.expense_date,
            payment_method=payload.payment_method,
            payment_reference=payload.payment_reference,
            invoice_number=payload.invoice_number,
            status=ExpenseStatus.DRAFT,
            account_id=payload.account_id,
            notes=payload.notes,
        )
        await self._repo.create_expense(expense)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_CREATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "expense_id": str(expense.id),
                    "expense_number": expense_number,
                    "amount": str(payload.amount),
                    "vendor": payload.vendor_name,
                },
            )
        return expense

    async def get_expense(self, expense_id: uuid.UUID) -> FinanceExpense:
        expense = await self._repo.get_expense_by_id(expense_id)
        if not expense:
            raise NotFoundError("Expense not found.")
        return expense

    async def update_expense(
        self,
        expense_id: uuid.UUID,
        payload: FinanceExpenseUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FinanceExpense:
        expense = await self._repo.get_expense_by_id(expense_id)
        if not expense:
            raise NotFoundError("Expense not found.")
        if expense.status not in (ExpenseStatus.DRAFT, ExpenseStatus.SUBMITTED):
            raise ValidationFailedError(
                "Only draft or submitted expenses can be edited."
            )
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "account_id" in update_data and update_data["account_id"]:
            account = await self._repo.get_account_by_id(update_data["account_id"])
            if not account:
                raise NotFoundError("Account not found.")
        for key, value in update_data.items():
            setattr(expense, key, value)
        await self._repo._session.flush()
        await self._repo._session.refresh(expense)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "expense_id": str(expense_id),
                    "changes": update_data,
                },
            )
        return expense

    async def list_expenses_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        category: ExpenseCategory | None = None,
        status: ExpenseStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PaginatedResponse[FinanceExpenseResponse]:
        results, total = await self._repo.list_expenses_paginated(
            page, sort, search_term, category, status, date_from, date_to
        )
        return PaginatedResponse(
            data=[FinanceExpenseResponse.model_validate(e) for e in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def approve_expense(
        self,
        expense_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FinanceExpense:
        expense = await self._repo.get_expense_by_id(expense_id)
        if not expense:
            raise NotFoundError("Expense not found.")
        if expense.status not in (ExpenseStatus.DRAFT, ExpenseStatus.SUBMITTED):
            raise ValidationFailedError(
                "Only draft or submitted expenses can be approved."
            )
        expense.status = ExpenseStatus.APPROVED
        expense.approved_by = actor_id
        expense.approved_at = datetime.now(UTC)
        await self._repo._session.flush()
        await self._repo._session.refresh(expense)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "expense_id": str(expense_id),
                    "action": "approved",
                },
            )
        return expense

    async def reject_expense(
        self,
        expense_id: uuid.UUID,
        reason: str,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FinanceExpense:
        expense = await self._repo.get_expense_by_id(expense_id)
        if not expense:
            raise NotFoundError("Expense not found.")
        if expense.status not in (ExpenseStatus.DRAFT, ExpenseStatus.SUBMITTED):
            raise ValidationFailedError(
                "Only draft or submitted expenses can be rejected."
            )
        expense.status = ExpenseStatus.REJECTED
        expense.rejection_reason = reason
        await self._repo._session.flush()
        await self._repo._session.refresh(expense)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "expense_id": str(expense_id),
                    "action": "rejected",
                    "reason": reason,
                },
            )
        return expense

    async def submit_expense(
        self,
        expense_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FinanceExpense:
        expense = await self._repo.get_expense_by_id(expense_id)
        if not expense:
            raise NotFoundError("Expense not found.")
        if expense.status != ExpenseStatus.DRAFT:
            raise ValidationFailedError("Only draft expenses can be submitted.")
        expense.status = ExpenseStatus.SUBMITTED
        await self._repo._session.flush()
        await self._repo._session.refresh(expense)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "expense_id": str(expense_id),
                    "action": "submitted",
                },
            )
        return expense

    async def pay_expense(
        self,
        expense_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> FinanceExpense:
        expense = await self._repo.get_expense_by_id(expense_id)
        if not expense:
            raise NotFoundError("Expense not found.")
        if expense.status != ExpenseStatus.APPROVED:
            raise ValidationFailedError("Only approved expenses can be marked as paid.")
        if expense.account_id:
            sequence = await self._repo.next_transaction_sequence()
            tx_number = f"TXN-{datetime.now(UTC).strftime('%Y%m%d')}-{sequence:05d}"
            expense_account = await self._repo.get_account_by_id(expense.account_id)
            cash_account = (
                await self._repo._session.execute(
                    sa.select(ChartOfAccounts).where(
                        ChartOfAccounts.account_type == AccountType.ASSET,
                        ChartOfAccounts.category.in_([AccountCategory.CASH, AccountCategory.BANK]),
                        ChartOfAccounts.deleted_at.is_(None),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            tx = FinancialTransaction(
                transaction_number=tx_number,
                transaction_type=TransactionType.EXPENSE,
                transaction_date=datetime.now(UTC).date(),
                amount=expense.amount,
                currency=expense.currency,
                description=f"Expense payment - {expense.title} ({expense.expense_number})",
                reference_type="finance_expense",
                reference_id=expense.id,
                status=TransactionStatus.POSTED,
            )
            await self._repo.create_transaction(tx)
            if expense_account and cash_account:
                entry1 = GeneralLedgerEntry(
                    account_id=expense_account.id,
                    transaction_id=tx.id,
                    debit_amount=expense.amount,
                    credit_amount=0,
                    entry_date=datetime.now(UTC).date(),
                    description=f"Expense {expense.expense_number}",
                )
                await self._repo.create_ledger_entry(entry1)
                entry2 = GeneralLedgerEntry(
                    account_id=cash_account.id,
                    transaction_id=tx.id,
                    debit_amount=0,
                    credit_amount=expense.amount,
                    entry_date=datetime.now(UTC).date(),
                    description=f"Expense {expense.expense_number}",
                )
                await self._repo.create_ledger_entry(entry2)
            expense.transaction_id = tx.id
        expense.status = ExpenseStatus.PAID
        await self._repo._session.flush()
        await self._repo._session.refresh(expense)
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_STATUS_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "expense_id": str(expense_id),
                    "action": "paid",
                    "transaction_id": str(expense.transaction_id) if expense.transaction_id else None,
                },
            )
        return expense

    async def soft_delete_expense(
        self,
        expense_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        expense = await self._repo.get_expense_by_id(expense_id)
        if not expense:
            raise NotFoundError("Expense not found.")
        if expense.status == ExpenseStatus.PAID:
            raise ValidationFailedError("Paid expenses cannot be deleted.")
        expense.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.FINANCE_TRANSACTION_DELETED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"expense_id": str(expense_id)},
            )

    async def process_refund(
        self,
        donation_id: uuid.UUID,
        reason: str,
        refund_amount: Decimal | None = None,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> RefundResponse:
        donation = await self._repo.get_donation_by_id(donation_id)
        if not donation:
            raise NotFoundError("Donation not found.")
        if donation.status == DonationStatus.REFUNDED:
            raise ConflictError("This donation has already been refunded.")
        if donation.status != DonationStatus.SUCCESS:
            raise ValidationFailedError(
                "Only successful donations can be refunded."
            )
        original_amount = Decimal(str(donation.amount))
        actual_refund = refund_amount if refund_amount and refund_amount <= original_amount else original_amount
        if actual_refund <= 0:
            raise ValidationFailedError("Refund amount must be greater than zero.")
        sequence = await self._repo.next_transaction_sequence()
        tx_number = f"RFD-{datetime.now(UTC).strftime('%Y%m%d')}-{sequence:05d}"
        income_account, cash_account = await self._get_reconcile_accounts()
        tx = FinancialTransaction(
            transaction_number=tx_number,
            transaction_type=TransactionType.REFUND,
            transaction_date=datetime.now(UTC).date(),
            amount=actual_refund,
            currency=donation.currency or "USD",
            description=f"Refund for donation {donation.id}: {reason}",
            reference_type="donation_refund",
            reference_id=donation_id,
            donation_id=donation_id,
            status=TransactionStatus.POSTED,
        )
        await self._repo.create_transaction(tx)
        if income_account and cash_account:
            entry1 = GeneralLedgerEntry(
                account_id=income_account.id,
                transaction_id=tx.id,
                debit_amount=actual_refund,
                credit_amount=0,
                entry_date=datetime.now(UTC).date(),
                description=f"Refund for donation {donation.id}",
            )
            await self._repo.create_ledger_entry(entry1)
            entry2 = GeneralLedgerEntry(
                account_id=cash_account.id,
                transaction_id=tx.id,
                debit_amount=0,
                credit_amount=actual_refund,
                entry_date=datetime.now(UTC).date(),
                description=f"Refund for donation {donation.id}",
            )
            await self._repo.create_ledger_entry(entry2)
        if actual_refund >= original_amount:
            donation.status = DonationStatus.REFUNDED
        else:
            donation.notes = (
                (donation.notes or "") + f"\nPartial refund of {actual_refund} processed: {reason}"
            ).strip()
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_REFUNDED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "donation_id": str(donation_id),
                    "refund_amount": str(actual_refund),
                    "original_amount": str(original_amount),
                    "reason": reason,
                    "transaction_number": tx_number,
                },
            )
        return RefundResponse(
            refund_id=tx.id,
            donation_id=donation_id,
            original_amount=original_amount,
            refund_amount=actual_refund,
            currency=donation.currency or "USD",
            status=donation.status.value,
            transaction_number=tx_number,
            refunded_at=datetime.now(UTC),
            reason=reason,
        )

    async def generate_80g_certificate(
        self,
        donation_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> TaxReceipt80GResponse:
        from pawguard.services.storage_service import StorageService

        donation = await self._repo.get_donation_by_id(donation_id)
        if not donation:
            raise NotFoundError("Donation not found.")
        if donation.status != DonationStatus.SUCCESS:
            raise ValidationFailedError(
                "80G certificates can only be generated for successful donations."
            )
        donor = donation.donor
        if not donor:
            raise NotFoundError("Donor profile not found.")
        if not donor.is_80g_eligible:
            raise ValidationFailedError(
                "This donor is not marked as 80G eligible. "
                "Please update the donor profile with PAN and eligibility details."
            )
        if not donor.pan_number:
            raise ValidationFailedError(
                "PAN number is required for 80G certificate generation."
            )
        donor_name = donor.full_name_for_80g or (
            donor.user.full_name if donor.user else "Donor"
        )
        receipt_number = f"80G-{donation.id.hex[:12].upper()}"
        donation_date = donation.created_at.date() if hasattr(donation.created_at, 'date') else donation.created_at
        try:
            pdf_bytes = await self._generate_80g_pdf(
                donor_name=donor_name,
                pan_number=donor.pan_number,
                amount=float(donation.amount),
                currency=donation.currency,
                donation_date=donation.created_at,
                receipt_number=receipt_number,
                address=donor.address_for_80g,
            )
            storage = StorageService()
            object_key = storage.build_object_key(
                folder="documents", filename=f"80g_{donation.id}.pdf"
            )
            import asyncio
            await asyncio.to_thread(
                storage.put_object,
                object_key=object_key,
                content=pdf_bytes,
                content_type="application/pdf",
            )
            certificate_url = storage.generate_presigned_download_url(object_key=object_key)
        except Exception:
            certificate_url = None

        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.DONATION_RECEIPT_ISSUED,
                actor_id=actor_id,
                ip_address="",
                user_agent="",
                metadata={
                    "donation_id": str(donation_id),
                    "certificate_type": "80G",
                    "receipt_number": receipt_number,
                },
            )
        return TaxReceipt80GResponse(
            donation_id=donation_id,
            donor_name=donor_name,
            pan_number=donor.pan_number,
            amount=Decimal(str(donation.amount)),
            currency=donation.currency or "USD",
            donation_date=donation_date,
            receipt_number=receipt_number,
            certificate_url=certificate_url,
            is_80g_eligible=True,
            generated_at=datetime.now(UTC),
        )

    async def _generate_80g_pdf(
        self,
        *,
        donor_name: str,
        pan_number: str,
        amount: float,
        currency: str,
        donation_date: datetime,
        receipt_number: str,
        address: str | None = None,
    ) -> bytes:
        from pawguard.core.config import get_settings
        from pawguard.core.pdf_generation import generate_80g_certificate

        settings = get_settings()
        return await __import__("asyncio").to_thread(
            generate_80g_certificate,
            donor_name=donor_name,
            pan_number=pan_number,
            amount=amount,
            currency=currency,
            donation_date=donation_date,
            receipt_number=receipt_number,
            org_name=settings.org_name,
            org_address=settings.org_address,
            address=address,
        )

    async def ensure_donation_receipt(
        self,
        donation_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> str:
        donation = await self._repo.get_donation_by_id(donation_id)
        if not donation:
            raise NotFoundError("Donation not found.")
        if donation.status != DonationStatus.SUCCESS:
            raise ValidationFailedError(
                "Receipts can only be generated for successful donations."
            )
        if donation.receipt_file_key:
            return donation.receipt_file_key
        from pawguard.modules.dog.repository import DogRepository
        from pawguard.modules.donation.repository import DonationRepository
        from pawguard.modules.donation.service import DonationService
        from pawguard.services.storage_service import StorageService
        donation_repo = DonationRepository(self._repo._session)
        dog_repo = DogRepository(self._repo._session)
        storage = StorageService()
        temp_service = DonationService(
            donation_repo, dog_repo, storage_service=storage, audit_service=self._audit,
        )
        refreshed = await donation_repo.get_donation_by_id(donation_id)
        if not refreshed:
            raise NotFoundError("Donation not found.")
        await temp_service._generate_receipt(refreshed)
        await self._repo._session.flush()
        await self._repo._session.refresh(donation)
        if not donation.receipt_file_key:
            raise NotFoundError("Failed to generate receipt for this donation.")
        return donation.receipt_file_key
