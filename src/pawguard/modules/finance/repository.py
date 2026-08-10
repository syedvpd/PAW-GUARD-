import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.donation.models import Donation, DonationStatus
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


class FinanceRepository:
    SEARCH_FIELDS_ACCOUNTS = ("account_code", "account_name", "description")
    SORTABLE_FIELDS_ACCOUNTS = {
        "account_code", "account_name", "account_type",
        "category", "current_balance", "created_at",
    }

    SEARCH_FIELDS_TRANSACTIONS = (
        "transaction_number", "description", "reference_type"
    )
    SORTABLE_FIELDS_TRANSACTIONS = {
        "transaction_number", "transaction_date", "amount",
        "status", "transaction_type", "created_at",
    }

    SEARCH_FIELDS_BUDGETS = ("name", "notes")
    SORTABLE_FIELDS_BUDGETS = {
        "name", "fiscal_year", "total_budget",
        "total_spent", "created_at",
    }

    SEARCH_FIELDS_RECURRING = ("name", "description")
    SORTABLE_FIELDS_RECURRING = {
        "name", "amount", "interval", "start_date", "is_active",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_account(self, account: ChartOfAccounts) -> ChartOfAccounts:
        self._session.add(account)
        await self._session.flush()
        return account

    async def get_account_by_id(
        self, account_id: uuid.UUID
    ) -> ChartOfAccounts | None:
        stmt = select(ChartOfAccounts).where(
            ChartOfAccounts.id == account_id,
            ChartOfAccounts.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_account_by_code(self, code: str) -> ChartOfAccounts | None:
        stmt = select(ChartOfAccounts).where(
            ChartOfAccounts.account_code == code,
            ChartOfAccounts.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_accounts_paginated(
        self, page: PageParams, sort: SortParams,
        search_term: str | None = None,
        account_type: AccountType | None = None,
        category: AccountCategory | None = None,
        is_active: bool | None = None,
    ) -> tuple[Sequence[ChartOfAccounts], int]:
        stmt = select(ChartOfAccounts).where(
            ChartOfAccounts.deleted_at.is_(None)
        )
        search_filter = build_search_filter(
            ChartOfAccounts, search_term, self.SEARCH_FIELDS_ACCOUNTS
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        if account_type is not None:
            stmt = stmt.where(ChartOfAccounts.account_type == account_type)
        if category is not None:
            stmt = stmt.where(ChartOfAccounts.category == category)
        if is_active is not None:
            stmt = stmt.where(ChartOfAccounts.is_active == is_active)
        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS_ACCOUNTS)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()
        return results, total

    async def list_accounts_all(self) -> Sequence[ChartOfAccounts]:
        stmt = select(ChartOfAccounts).where(
            ChartOfAccounts.deleted_at.is_(None)
        ).order_by(ChartOfAccounts.account_code)
        return (await self._session.execute(stmt)).scalars().all()

    async def next_transaction_sequence(self) -> int:
        stmt = text("SELECT nextval('financial_transaction_seq')")
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def create_transaction(
        self, tx: FinancialTransaction
    ) -> FinancialTransaction:
        self._session.add(tx)
        await self._session.flush()
        return tx

    async def get_transaction_by_id(
        self, tx_id: uuid.UUID
    ) -> FinancialTransaction | None:
        stmt = select(FinancialTransaction).options(
            selectinload(FinancialTransaction.entries)
            .selectinload(GeneralLedgerEntry.account)
        ).where(
            FinancialTransaction.id == tx_id,
            FinancialTransaction.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_transaction_by_number(
        self, number: str
    ) -> FinancialTransaction | None:
        stmt = select(FinancialTransaction).where(
            FinancialTransaction.transaction_number == number
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_transactions_paginated(
        self, page: PageParams, sort: SortParams,
        search_term: str | None = None,
        transaction_type: TransactionType | None = None,
        status: TransactionStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[Sequence[FinancialTransaction], int]:
        stmt = select(FinancialTransaction).where(
            FinancialTransaction.deleted_at.is_(None)
        )
        search_filter = build_search_filter(
            FinancialTransaction, search_term,
            self.SEARCH_FIELDS_TRANSACTIONS,
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        if transaction_type is not None:
            stmt = stmt.where(
                FinancialTransaction.transaction_type == transaction_type
            )
        if status is not None:
            stmt = stmt.where(FinancialTransaction.status == status)
        if date_from is not None:
            stmt = stmt.where(
                FinancialTransaction.transaction_date >= date_from
            )
        if date_to is not None:
            stmt = stmt.where(
                FinancialTransaction.transaction_date <= date_to
            )
        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS_TRANSACTIONS)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()
        return results, total

    async def create_ledger_entry(
        self, entry: GeneralLedgerEntry
    ) -> GeneralLedgerEntry:
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_ledger_entries(
        self, transaction_id: uuid.UUID
    ) -> Sequence[GeneralLedgerEntry]:
        stmt = select(GeneralLedgerEntry).options(
            selectinload(GeneralLedgerEntry.account)
        ).where(GeneralLedgerEntry.transaction_id == transaction_id)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_finance_summary(
        self, period_start: date, period_end: date
    ) -> dict[str, Any]:
        manual_income = await self._session.execute(
            select(func.coalesce(func.sum(FinancialTransaction.amount), 0))
            .where(
                FinancialTransaction.transaction_type
                == TransactionType.INCOME,
                FinancialTransaction.status.in_([
                    TransactionStatus.POSTED,
                    TransactionStatus.RECONCILED,
                ]),
                FinancialTransaction.transaction_date.between(
                    period_start, period_end
                ),
                FinancialTransaction.deleted_at.is_(None),
            )
        )
        expenses = await self._session.execute(
            select(func.coalesce(func.sum(FinancialTransaction.amount), 0))
            .where(
                FinancialTransaction.transaction_type
                == TransactionType.EXPENSE,
                FinancialTransaction.status.in_([
                    TransactionStatus.POSTED,
                    TransactionStatus.RECONCILED,
                ]),
                FinancialTransaction.transaction_date.between(
                    period_start, period_end
                ),
                FinancialTransaction.deleted_at.is_(None),
            )
        )
        pending = await self._session.execute(
            select(func.count(FinancialTransaction.id)).where(
                FinancialTransaction.status == TransactionStatus.PENDING,
                FinancialTransaction.deleted_at.is_(None),
            )
        )
        unreconciled = await self._session.execute(
            select(func.count(FinancialTransaction.id)).where(
                FinancialTransaction.status != TransactionStatus.RECONCILED,
                FinancialTransaction.deleted_at.is_(None),
            )
        )
        donation_tx = await self._session.execute(
            select(
                func.coalesce(func.sum(FinancialTransaction.amount), 0)
            ).where(
                FinancialTransaction.transaction_type
                == TransactionType.RECONCILIATION,
                FinancialTransaction.status == TransactionStatus.RECONCILED,
                FinancialTransaction.transaction_date.between(
                    period_start, period_end
                ),
                FinancialTransaction.deleted_at.is_(None),
            )
        )
        # Self-healing income: successful donations that have not yet been
        # posted into the finance ledger still represent real income. Once a
        # donation is reconciled it appears via its RECONCILIATION transaction
        # instead, so nothing is double counted.
        unreconciled_donation_income = await self._session.execute(
            select(func.coalesce(func.sum(Donation.amount), 0))
            .where(
                Donation.status == DonationStatus.SUCCESS,
                func.date(Donation.created_at).between(
                    period_start, period_end
                ),
                Donation.id.notin_(
                    select(FinancialTransaction.donation_id).where(
                        FinancialTransaction.donation_id.isnot(None),
                        FinancialTransaction.status
                        == TransactionStatus.RECONCILED,
                    )
                ),
            )
        )
        income_total = (
            float(manual_income.scalar_one())
            + float(donation_tx.scalar_one())
            + float(unreconciled_donation_income.scalar_one())
        )
        expenses_total = float(expenses.scalar_one())
        return {
            "total_income": income_total,
            "total_expenses": expenses_total,
            "net_balance": income_total - expenses_total,
            "pending_transactions": pending.scalar_one(),
            "unreconciled_count": unreconciled.scalar_one(),
            "total_donations_reconciled": donation_tx.scalar_one(),
            "period_start": period_start,
            "period_end": period_end,
        }

    async def reconcile_donation(
        self, donation_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> None:
        stmt = update(FinancialTransaction).where(
            FinancialTransaction.id == transaction_id
        ).values(
            status=TransactionStatus.RECONCILED,
            reconciled_at=datetime.utcnow(),
            donation_id=donation_id,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_unreconciled_donations(self) -> Sequence[Donation]:
        stmt = select(Donation).where(
            Donation.status == DonationStatus.SUCCESS,
            Donation.id.notin_(
                select(FinancialTransaction.donation_id).where(
                    FinancialTransaction.donation_id.isnot(None),
                    FinancialTransaction.status
                    == TransactionStatus.RECONCILED,
                )
            ),
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_donation_by_id(self, donation_id: uuid.UUID) -> Donation | None:
        stmt = select(Donation).where(Donation.id == donation_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def is_donation_reconciled(self, donation_id: uuid.UUID) -> bool:
        stmt = select(
            func.count(FinancialTransaction.id)
        ).where(
            FinancialTransaction.donation_id == donation_id,
            FinancialTransaction.status == TransactionStatus.RECONCILED,
        )
        count = (await self._session.execute(stmt)).scalar_one()
        return count > 0

    async def get_donation_reconciliation_summary(self) -> dict[str, Any]:
        total = await self._session.execute(
            select(
                func.count(Donation.id),
                func.coalesce(func.sum(Donation.amount), 0),
            ).where(
                Donation.status == DonationStatus.SUCCESS,
            )
        )
        total_count, total_amount = total.one()
        reconciled_tx = await self._session.execute(
            select(
                func.count(FinancialTransaction.id),
                func.coalesce(func.sum(FinancialTransaction.amount), 0),
            ).where(
                FinancialTransaction.status
                == TransactionStatus.RECONCILED,
                FinancialTransaction.donation_id.isnot(None),
                FinancialTransaction.deleted_at.is_(None),
            )
        )
        reconciled_count, reconciled_amount = reconciled_tx.one()
        return {
            "total_donations": total_count,
            "total_amount": total_amount,
            "reconciled_count": reconciled_count,
            "reconciled_amount": reconciled_amount,
            "unreconciled_count": total_count - reconciled_count,
            "unreconciled_amount": total_amount - reconciled_amount,
        }

    async def get_account_balances(self) -> Sequence[ChartOfAccounts]:
        stmt = select(ChartOfAccounts).where(
            ChartOfAccounts.deleted_at.is_(None),
            ChartOfAccounts.is_active.is_(True),
        ).order_by(ChartOfAccounts.account_code)
        return (await self._session.execute(stmt)).scalars().all()

    async def update_account_balance(
        self, account_id: uuid.UUID, amount: Decimal
    ) -> None:
        stmt = select(ChartOfAccounts).where(
            ChartOfAccounts.id == account_id
        )
        account = (await self._session.execute(stmt)).scalar_one_or_none()
        if account:
            account.current_balance = (
                ChartOfAccounts.current_balance + amount
            )
            await self._session.flush()

    async def get_pnl(self, period_start: date, period_end: date) -> dict[str, Any]:
        income_stmt = select(
            ChartOfAccounts.account_code,
            ChartOfAccounts.account_name,
            func.coalesce(func.sum(
                GeneralLedgerEntry.credit_amount
                - GeneralLedgerEntry.debit_amount
            ), 0),
        ).join(
            GeneralLedgerEntry,
            GeneralLedgerEntry.account_id == ChartOfAccounts.id,
        ).where(
            ChartOfAccounts.account_type == AccountType.INCOME,
            GeneralLedgerEntry.entry_date.between(
                period_start, period_end
            ),
        ).group_by(
            ChartOfAccounts.id, ChartOfAccounts.account_code,
            ChartOfAccounts.account_name,
        )
        expense_stmt = select(
            ChartOfAccounts.account_code,
            ChartOfAccounts.account_name,
            func.coalesce(func.sum(
                GeneralLedgerEntry.debit_amount
                - GeneralLedgerEntry.credit_amount
            ), 0),
        ).join(
            GeneralLedgerEntry,
            GeneralLedgerEntry.account_id == ChartOfAccounts.id,
        ).where(
            ChartOfAccounts.account_type == AccountType.EXPENSE,
            GeneralLedgerEntry.entry_date.between(
                period_start, period_end
            ),
        ).group_by(
            ChartOfAccounts.id, ChartOfAccounts.account_code,
            ChartOfAccounts.account_name,
        )
        income_rows = (await self._session.execute(income_stmt)).all()
        expense_rows = (await self._session.execute(expense_stmt)).all()
        total_income = sum(float(r[2]) for r in income_rows)
        total_expenses = sum(float(r[2]) for r in expense_rows)
        return {
            "period_start": (
                period_start.isoformat()
                if hasattr(period_start, 'isoformat')
                else str(period_start)
            ),
            "period_end": (
                period_end.isoformat()
                if hasattr(period_end, 'isoformat')
                else str(period_end)
            ),
            "income": [
                {"account_code": r[0], "account_name": r[1],
                 "amount": float(r[2])}
                for r in income_rows
            ],
            "expenses": [
                {"account_code": r[0], "account_name": r[1],
                 "amount": float(r[2])}
                for r in expense_rows
            ],
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_income": total_income - total_expenses,
        }

    async def create_budget(self, budget: Budget) -> Budget:
        self._session.add(budget)
        await self._session.flush()
        return budget

    async def get_budget_by_id(
        self, budget_id: uuid.UUID
    ) -> Budget | None:
        stmt = select(Budget).options(
            selectinload(Budget.items).selectinload(BudgetItem.account)
        ).where(
            Budget.id == budget_id,
            Budget.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_budgets_paginated(
        self, page: PageParams, sort: SortParams,
        search_term: str | None = None,
        fiscal_year: int | None = None,
        is_active: bool | None = None,
    ) -> tuple[Sequence[Budget], int]:
        stmt = select(Budget).options(
            selectinload(Budget.items).selectinload(BudgetItem.account)
        ).where(Budget.deleted_at.is_(None))
        search_filter = build_search_filter(
            Budget, search_term, self.SEARCH_FIELDS_BUDGETS
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        if fiscal_year is not None:
            stmt = stmt.where(Budget.fiscal_year == fiscal_year)
        if is_active is not None:
            stmt = stmt.where(Budget.is_active == is_active)
        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS_BUDGETS)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()
        return results, total

    async def create_budget_item(self, item: BudgetItem) -> BudgetItem:
        self._session.add(item)
        await self._session.flush()
        return item

    async def create_recurring(
        self, rtx: RecurringTransaction
    ) -> RecurringTransaction:
        self._session.add(rtx)
        await self._session.flush()
        return rtx

    async def get_recurring_by_id(
        self, rtx_id: uuid.UUID
    ) -> RecurringTransaction | None:
        stmt = select(RecurringTransaction).where(
            RecurringTransaction.id == rtx_id,
            RecurringTransaction.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_recurring_paginated(
        self, page: PageParams, sort: SortParams,
        search_term: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[Sequence[RecurringTransaction], int]:
        stmt = select(RecurringTransaction).where(
            RecurringTransaction.deleted_at.is_(None)
        )
        search_filter = build_search_filter(
            RecurringTransaction, search_term,
            self.SEARCH_FIELDS_RECURRING,
        )
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        if is_active is not None:
            stmt = stmt.where(
                RecurringTransaction.is_active == is_active
            )
        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS_RECURRING)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()
        return results, total

    async def list_by_ids(
        self, model: type[Any], ids: list[uuid.UUID]
    ) -> Sequence[Any]:
        stmt = select(model).where(
            model.id.in_(ids), model.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def bulk_soft_delete(self, model, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        stmt = (
            update(model)
            .where(model.id.in_(ids), model.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def bulk_update_status(
        self, model: type[Any], ids: list[uuid.UUID],
        status_field: str, status_value: str,
    ) -> int:
        stmt = update(model).where(
            model.id.in_(ids), model.deleted_at.is_(None)
        ).values(**{status_field: status_value})
        result = await self._session.execute(stmt)
        return result.rowcount or 0  # type: ignore[attr-defined]
