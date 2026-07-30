"""add_finance_module

Revision ID: deac4a16c5fe
Revises: a3b9c8d7e6f5
Create Date: 2026-07-30 05:07:14.779192

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "deac4a16c5fe"
down_revision: Union[str, None] = "a3b9c8d7e6f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chart_of_accounts",
        sa.Column("account_code", sa.String(length=32), nullable=False),
        sa.Column("account_name", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("parent_account_id", sa.UUID(), nullable=True),
        sa.Column("opening_balance", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("current_balance", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_account_id"], ["chart_of_accounts.id"],
            name=op.f("fk_chart_of_accounts_parent_account_id_chart_of_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chart_of_accounts")),
    )
    op.create_index(
        op.f("ix_chart_of_accounts_account_code"),
        "chart_of_accounts", ["account_code"], unique=True,
    )
    op.create_index(
        op.f("ix_chart_of_accounts_account_type"),
        "chart_of_accounts", ["account_type"], unique=False,
    )
    op.create_index(
        op.f("ix_chart_of_accounts_category"),
        "chart_of_accounts", ["category"], unique=False,
    )

    op.create_table(
        "financial_transactions",
        sa.Column("transaction_number", sa.String(length=64), nullable=False),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reference_type", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.UUID(), nullable=True),
        sa.Column("donation_id", sa.UUID(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["donation_id"], ["donations.id"],
            name=op.f("fk_financial_transactions_donation_id_donations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reconciled_by"], ["users.id"],
            name=op.f("fk_financial_transactions_reconciled_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_transactions")),
    )
    op.create_index(
        op.f("ix_financial_transactions_transaction_number"),
        "financial_transactions", ["transaction_number"], unique=True,
    )
    op.create_index(
        op.f("ix_financial_transactions_transaction_type"),
        "financial_transactions", ["transaction_type"], unique=False,
    )
    op.create_index(
        op.f("ix_financial_transactions_status"),
        "financial_transactions", ["status"], unique=False,
    )
    op.create_index(
        op.f("ix_financial_transactions_transaction_date"),
        "financial_transactions", ["transaction_date"], unique=False,
    )

    op.create_table(
        "general_ledger_entries",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("debit_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("credit_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["chart_of_accounts.id"],
            name=op.f("fk_general_ledger_entries_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["financial_transactions.id"],
            name=op.f("fk_general_ledger_entries_transaction_id_financial_transactions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_general_ledger_entries")),
    )
    op.create_index(
        op.f("ix_general_ledger_entries_account_id"),
        "general_ledger_entries", ["account_id"], unique=False,
    )
    op.create_index(
        op.f("ix_general_ledger_entries_transaction_id"),
        "general_ledger_entries", ["transaction_id"], unique=False,
    )
    op.create_index(
        op.f("ix_general_ledger_entries_entry_date"),
        "general_ledger_entries", ["entry_date"], unique=False,
    )

    op.create_table(
        "recurring_transactions",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("interval", sa.String(length=32), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("debit_account_id", sa.UUID(), nullable=False),
        sa.Column("credit_account_id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_generated", sa.Date(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["debit_account_id"], ["chart_of_accounts.id"],
            name=op.f("fk_recurring_transactions_debit_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["credit_account_id"], ["chart_of_accounts.id"],
            name=op.f("fk_recurring_transactions_credit_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_transactions")),
    )

    op.create_table(
        "budgets",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("total_budget", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total_spent", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
    )
    op.create_index(
        op.f("ix_budgets_fiscal_year"),
        "budgets", ["fiscal_year"], unique=False,
    )

    op.create_table(
        "budget_items",
        sa.Column("budget_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("spent_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["budget_id"], ["budgets.id"],
            name=op.f("fk_budget_items_budget_id_budgets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["chart_of_accounts.id"],
            name=op.f("fk_budget_items_account_id_chart_of_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budget_items")),
    )
    op.create_index(
        op.f("ix_budget_items_budget_id"),
        "budget_items", ["budget_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_table("budget_items")
    op.drop_table("budgets")
    op.drop_table("recurring_transactions")
    op.drop_table("general_ledger_entries")
    op.drop_table("financial_transactions")
    op.drop_table("chart_of_accounts")
