"""add shift attendance status lifecycle (no-show / cancelled)

Revision ID: e39162ae1bfc
Revises: 2e288a4af48e
Create Date: 2026-08-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e39162ae1bfc"
down_revision: Union[str, None] = "2e288a4af48e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shift_attendances",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="claimed"),
    )
    op.add_column("shift_attendances", sa.Column("no_show_reason", sa.Text(), nullable=True))
    op.add_column("shift_attendances", sa.Column("no_show_marked_by", sa.UUID(), nullable=True))
    op.add_column(
        "shift_attendances", sa.Column("no_show_marked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("shift_attendances", sa.Column("cancelled_reason", sa.Text(), nullable=True))
    op.add_column("shift_attendances", sa.Column("cancelled_by", sa.UUID(), nullable=True))
    op.add_column(
        "shift_attendances", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "shift_attendances", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_shift_attendances_status", "shift_attendances", ["status"])
    op.create_foreign_key(
        "fk_shift_attendances_no_show_marked_by",
        "shift_attendances",
        "users",
        ["no_show_marked_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_shift_attendances_cancelled_by",
        "shift_attendances",
        "users",
        ["cancelled_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Backfill: any attendance already checked out/in under the old
    # timestamp-only model must carry a status consistent with those
    # timestamps, not the "claimed" default just applied.
    op.execute(
        "UPDATE shift_attendances SET status = 'checked_out' WHERE check_out_at IS NOT NULL"
    )
    op.execute(
        "UPDATE shift_attendances SET status = 'checked_in' "
        "WHERE check_in_at IS NOT NULL AND check_out_at IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_shift_attendances_cancelled_by", "shift_attendances", type_="foreignkey")
    op.drop_constraint("fk_shift_attendances_no_show_marked_by", "shift_attendances", type_="foreignkey")
    op.drop_index("ix_shift_attendances_status", table_name="shift_attendances")
    op.drop_column("shift_attendances", "reminder_sent_at")
    op.drop_column("shift_attendances", "cancelled_at")
    op.drop_column("shift_attendances", "cancelled_by")
    op.drop_column("shift_attendances", "cancelled_reason")
    op.drop_column("shift_attendances", "no_show_marked_at")
    op.drop_column("shift_attendances", "no_show_marked_by")
    op.drop_column("shift_attendances", "no_show_reason")
    op.drop_column("shift_attendances", "status")
