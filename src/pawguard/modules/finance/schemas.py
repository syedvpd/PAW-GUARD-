import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from pawguard.modules.finance.models import (
    AccountCategory,
    AccountType,
    RecurringInterval,
    TransactionStatus,
    TransactionType,
)


class ChartOfAccountsCreate(BaseModel):
    account_code: str = Field(..., min_length=2, max_length=32, examples=["5010"])
    account_name: str = Field(..., min_length=2, max_length=255, examples=["Veterinary Expenses"])
    account_type: AccountType = Field(..., examples=["expense"])
    category: AccountCategory = Field(..., examples=["medical_expense"])
    description: str | None = Field(None, examples=["Tracks all veterinary and medical costs."])
    parent_account_id: uuid.UUID | None = None
    opening_balance: Decimal = Field(default=Decimal("0.00"), ge=0, examples=[0.0])


class ChartOfAccountsUpdate(BaseModel):
    account_name: str | None = Field(None, examples=["Veterinary Expenses"])
    description: str | None = Field(None, examples=["Updated description."])
    is_active: bool | None = Field(None, examples=[True])
    parent_account_id: uuid.UUID | None = None


class ChartOfAccountsResponse(BaseModel):
    id: uuid.UUID
    account_code: str
    account_name: str
    account_type: AccountType
    category: AccountCategory
    description: str | None
    is_active: bool
    parent_account_id: uuid.UUID | None
    opening_balance: Decimal
    current_balance: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinancialTransactionCreate(BaseModel):
    transaction_type: TransactionType = Field(..., examples=["expense"])
    transaction_date: date = Field(..., examples=["2026-07-22"])
    amount: Decimal = Field(..., gt=0, examples=[150.0])
    currency: str = Field(default="USD", min_length=3, max_length=3, examples=["USD"])
    description: str | None = Field(None, examples=["Vet supplies restock"])
    reference_type: str | None = Field(None, examples=["rescue_case"])
    reference_id: uuid.UUID | None = None
    donation_id: uuid.UUID | None = None
    debit_account_id: uuid.UUID
    credit_account_id: uuid.UUID


class FinancialTransactionUpdate(BaseModel):
    description: str | None = Field(None, examples=["Updated: includes delivery fee."])
    status: TransactionStatus | None = Field(None, examples=["posted"])


class FinancialTransactionResponse(BaseModel):
    id: uuid.UUID
    transaction_number: str
    transaction_type: TransactionType
    status: TransactionStatus
    transaction_date: date
    amount: Decimal
    currency: str
    description: str | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    donation_id: uuid.UUID | None
    reconciled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneralLedgerEntryResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    transaction_id: uuid.UUID
    debit_amount: Decimal
    credit_amount: Decimal
    entry_date: date
    description: str | None
    account: ChartOfAccountsResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class RecurringTransactionCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, examples=["Monthly Rent"])
    description: str | None = Field(None, examples=["Shelter facility lease payment."])
    transaction_type: TransactionType = Field(..., examples=["expense"])
    amount: Decimal = Field(..., gt=0, examples=[2000.0])
    currency: str = Field(default="USD", min_length=3, max_length=3, examples=["USD"])
    interval: RecurringInterval = Field(..., examples=["monthly"])
    day_of_month: int | None = Field(None, ge=1, le=31, examples=[1])
    day_of_week: int | None = Field(None, ge=0, le=6, examples=[1])
    start_date: date = Field(..., examples=["2026-08-01"])
    end_date: date | None = Field(None, examples=["2027-08-01"])
    debit_account_id: uuid.UUID
    credit_account_id: uuid.UUID


class RecurringTransactionUpdate(BaseModel):
    name: str | None = Field(None, examples=["Monthly Rent - Updated"])
    description: str | None = Field(None, examples=["Updated description."])
    amount: Decimal | None = Field(default=None, gt=0, examples=[2100.0])
    is_active: bool | None = Field(None, examples=[True])
    end_date: date | None = Field(None, examples=["2027-08-01"])


class RecurringTransactionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    transaction_type: TransactionType
    amount: Decimal
    currency: str
    interval: RecurringInterval
    day_of_month: int | None
    day_of_week: int | None
    start_date: date
    end_date: date | None
    is_active: bool
    last_generated: date | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, examples=["Annual 2026"])
    fiscal_year: int = Field(..., ge=2020, le=2100, examples=[2026])
    start_date: date = Field(..., examples=["2026-01-01"])
    end_date: date = Field(..., examples=["2026-12-31"])
    notes: str | None = Field(None, examples=["Approved by the board on 2025-12-15."])


class BudgetUpdate(BaseModel):
    name: str | None = Field(None, examples=["Annual 2026 - Revised"])
    notes: str | None = Field(None, examples=["Revised after Q2 review."])
    is_active: bool | None = Field(None, examples=[True])


class BudgetItemCreate(BaseModel):
    account_id: uuid.UUID
    allocated_amount: Decimal = Field(..., gt=0, examples=[5000.0])


class BudgetResponse(BaseModel):
    id: uuid.UUID
    name: str
    fiscal_year: int
    start_date: date
    end_date: date
    total_budget: Decimal
    total_spent: Decimal
    notes: str | None
    is_active: bool
    items: list["BudgetItemResponse"] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BudgetItemResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    allocated_amount: Decimal
    spent_amount: Decimal
    account: ChartOfAccountsResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class FinanceSummary(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    pending_transactions: int
    unreconciled_count: int
    total_donations_reconciled: Decimal
    period_start: date
    period_end: date


class AccountBalanceResponse(BaseModel):
    id: uuid.UUID
    account_code: str
    account_name: str
    account_type: AccountType
    category: AccountCategory
    opening_balance: Decimal
    current_balance: Decimal

    model_config = ConfigDict(from_attributes=True)


class DonationReconciliationResponse(BaseModel):
    total_donations: int
    total_amount: Decimal
    reconciled_count: int
    reconciled_amount: Decimal
    unreconciled_count: int
    unreconciled_amount: Decimal


class DonationReconcileRequest(BaseModel):
    """Request body for reconciling donations into the finance ledger.

    Unknown fields (e.g. ``dog_id``, ``file_id``, ``start_date``) are rejected
    with a 422 so callers cannot silently pass ignored IDs.
    """

    donation_ids: list[uuid.UUID] | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        description=(
            "Optional subset of successful donations to reconcile. "
            "When omitted, all unreconciled successful donations are reconciled."
        ),
        examples=[["3fa85f64-5717-4562-b3fc-2c963f66afa6"]],
    )

    model_config = ConfigDict(extra="forbid")
