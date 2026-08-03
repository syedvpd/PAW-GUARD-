"""add_transaction_number_sequence

Revision ID: f3a0b1c2d3e4
Revises: e9f0a1b2c3d4
Create Date: 2026-08-02 18:10:00.000000

Replaces the full-table COUNT(*) receipt-number generator in the finance
module with a dedicated DB sequence. The old generator read the whole
`financial_transactions` table once per created transaction (O(N) full-table
scans inside a batch) and produced duplicate `transaction_number` values under
concurrency (the column is UNIQUE). A sequence gives a cheap, atomic,
collision-free suffix for `TXN-` and `DR-` numbers.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f3a0b1c2d3e4"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS financial_transaction_seq")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS financial_transaction_seq")
