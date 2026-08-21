import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pawguard.db.base import Base
from pawguard.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    pass


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"


class AccountCategory(StrEnum):
    CASH = "cash"
    BANK = "bank"
    DONATION_INCOME = "donation_income"
    SPONSORSHIP_INCOME = "sponsorship_income"
    ADOPTION_FEE = "adoption_fee"
    MEDICAL_EXPENSE = "medical_expense"
    SHELTER_EXPENSE = "shelter_expense"
    VETERINARY_EXPENSE = "veterinary_expense"
    SUPPLIES_EXPENSE = "supplies_expense"
    SALARY_EXPENSE = "salary_expense"
    UTILITY_EXPENSE = "utility_expense"
    TRANSPORT_EXPENSE = "transport_expense"
    RECEIVABLE = "receivable"
    PAYABLE = "payable"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    RECONCILIATION = "reconciliation"
    REFUND = "refund"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    POSTED = "posted"
    RECONCILED = "reconciled"
    VOIDED = "voided"


class RecurringInterval(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class ChartOfAccounts(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "chart_of_accounts"

    account_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(String(32), nullable=False, index=True)
    category: Mapped[AccountCategory] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    parent_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )

    children: Mapped[list["ChartOfAccounts"]] = relationship(
        "ChartOfAccounts",
        backref="parent",
        remote_side="ChartOfAccounts.id",
        lazy="selectin",
    )


class GeneralLedgerEntry(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "general_ledger_entries"

    __table_args__ = (
        Index("ix_general_ledger_entries_account_id_entry_date", "account_id", "entry_date"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("financial_transactions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped["ChartOfAccounts"] = relationship("ChartOfAccounts", lazy="joined")
    transaction: Mapped["FinancialTransaction"] = relationship(
        "FinancialTransaction", lazy="joined"
    )


class FinancialTransaction(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "financial_transactions"

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_financial_transactions_amount_positive"),
    )

    transaction_number: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        String(32), nullable=False, index=True
    )
    status: Mapped[TransactionStatus] = mapped_column(
        String(32),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True,
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    donation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("donations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    entries: Mapped[list["GeneralLedgerEntry"]] = relationship(
        "GeneralLedgerEntry",
        back_populates="transaction",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RecurringTransaction(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "recurring_transactions"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_type: Mapped[TransactionType] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    interval: Mapped[RecurringInterval] = mapped_column(String(32), nullable=False)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    debit_account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    credit_account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_generated: Mapped[date | None] = mapped_column(Date, nullable=True)


class Budget(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "budgets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_budget: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    items: Mapped[list["BudgetItem"]] = relationship(
        "BudgetItem",
        back_populates="budget",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class BudgetItem(UUIDPkMixin, TimestampMixin, AuditMixin, Base):
    __tablename__ = "budget_items"

    budget_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    spent_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )

    budget: Mapped["Budget"] = relationship("Budget", back_populates="items", lazy="joined")
    account: Mapped["ChartOfAccounts"] = relationship("ChartOfAccounts", lazy="joined")


class ExpenseStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class ExpenseCategory(StrEnum):
    MEDICAL = "medical"
    VETERINARY = "veterinary"
    FOOD = "food"
    SUPPLIES = "supplies"
    SHELTER = "shelter"
    TRANSPORT = "transport"
    UTILITIES = "utilities"
    SALARY = "salary"
    MAINTENANCE = "maintenance"
    OTHER = "other"


class PaymentMethod(StrEnum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    CREDIT_CARD = "credit_card"
    UPI = "upi"
    OTHER = "other"


class FinanceExpense(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "finance_expenses"

    __table_args__ = (CheckConstraint("amount > 0", name="ck_finance_expenses_amount_positive"),)

    expense_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(String(64), nullable=False, index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor_gstin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        String(32), nullable=False, default=PaymentMethod.CASH
    )
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[ExpenseStatus] = mapped_column(
        String(32), nullable=False, default=ExpenseStatus.DRAFT, index=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("financial_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped["ChartOfAccounts | None"] = relationship("ChartOfAccounts", lazy="joined")
    transaction: Mapped["FinancialTransaction | None"] = relationship(
        "FinancialTransaction", lazy="joined"
    )
