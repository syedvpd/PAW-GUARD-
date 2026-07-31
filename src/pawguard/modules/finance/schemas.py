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
    account_code: str = Field(..., min_length=2, max_length=32)
    account_name: str = Field(..., min_length=2, max_length=255)
    account_type: AccountType
    category: AccountCategory
    description: str | None = None
    parent_account_id: uuid.UUID | None = None
    opening_balance: Decimal = Field(default=Decimal("0.00"), ge=0)


class ChartOfAccountsUpdate(BaseModel):
    account_name: str | None = None
    description: str | None = None
    is_active: bool | None = None
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
    transaction_type: TransactionType
    transaction_date: date
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    description: str | None = None
    reference_type: str | None = None
    reference_id: uuid.UUID | None = None
    donation_id: uuid.UUID | None = None
    debit_account_id: uuid.UUID
    credit_account_id: uuid.UUID


class FinancialTransactionUpdate(BaseModel):
    description: str | None = None
    status: TransactionStatus | None = None


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
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    transaction_type: TransactionType
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    interval: RecurringInterval
    day_of_month: int | None = Field(None, ge=1, le=31)
    day_of_week: int | None = Field(None, ge=0, le=6)
    start_date: date
    end_date: date | None = None
    debit_account_id: uuid.UUID
    credit_account_id: uuid.UUID


class RecurringTransactionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None
    end_date: date | None = None


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
    name: str = Field(..., min_length=2, max_length=255)
    fiscal_year: int = Field(..., ge=2020, le=2100)
    start_date: date
    end_date: date
    notes: str | None = None


class BudgetUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class BudgetItemCreate(BaseModel):
    account_id: uuid.UUID
    allocated_amount: Decimal = Field(..., gt=0)


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
