"""add finance_expenses table, donor 80G fields, donation REFUNDED status

Revision ID: e1f2g3h4i5j6
Revises: d4e5f6a7b8c9
Create Date: 2026-08-19 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "e1f2g3h4i5j6"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finance_expenses",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("expense_number", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("category", sa.String(64), nullable=False, index=True),
        sa.Column("vendor_name", sa.String(255), nullable=False),
        sa.Column("vendor_contact", sa.String(255), nullable=True),
        sa.Column("vendor_gstin", sa.String(64), nullable=True),
        sa.Column("expense_date", sa.Date, nullable=False, index=True),
        sa.Column("payment_method", sa.String(32), nullable=False, server_default="cash"),
        sa.Column("payment_reference", sa.String(255), nullable=True),
        sa.Column("invoice_number", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft", index=True),
        sa.Column("approved_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("account_id", PG_UUID(as_uuid=True), sa.ForeignKey("chart_of_accounts.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("transaction_id", PG_UUID(as_uuid=True), sa.ForeignKey("financial_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_finance_expenses_amount_positive"),
    )

    op.add_column(
        "donor_profiles",
        sa.Column("pan_number", sa.String(20), nullable=True),
    )
    op.add_column(
        "donor_profiles",
        sa.Column("full_name_for_80g", sa.String(255), nullable=True),
    )
    op.add_column(
        "donor_profiles",
        sa.Column("address_for_80g", sa.Text, nullable=True),
    )
    op.add_column(
        "donor_profiles",
        sa.Column("is_80g_eligible", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("donor_profiles", "is_80g_eligible")
    op.drop_column("donor_profiles", "address_for_80g")
    op.drop_column("donor_profiles", "full_name_for_80g")
    op.drop_column("donor_profiles", "pan_number")
    op.drop_table("finance_expenses")
