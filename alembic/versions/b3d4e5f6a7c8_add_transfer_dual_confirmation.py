"""add_transfer_dual_confirmation

Inter-facility transfers (FacilityTransfer) previously completed on a single
confirm call from either side, letting the requesting facility unilaterally
"confirm" its own transfer. The PRR requires both the sending and receiving
facility to separately confirm before a transfer completes; this adds the
tracking columns for that.

Revision ID: b3d4e5f6a7c8
Revises: b2e6f4a1c9d7
Create Date: 2026-07-30 21:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3d4e5f6a7c8"
down_revision: Union[str, None] = "b2e6f4a1c9d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "facility_transfers",
        sa.Column("sender_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "facility_transfers",
        sa.Column("sender_confirmed_by", sa.UUID(), nullable=True),
    )
    op.add_column(
        "facility_transfers",
        sa.Column("receiver_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "facility_transfers",
        sa.Column("receiver_confirmed_by", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_facility_transfers_sender_confirmed_by_users",
        "facility_transfers", "users",
        ["sender_confirmed_by"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_facility_transfers_receiver_confirmed_by_users",
        "facility_transfers", "users",
        ["receiver_confirmed_by"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_facility_transfers_receiver_confirmed_by_users",
        "facility_transfers", type_="foreignkey",
    )
    op.drop_constraint(
        "fk_facility_transfers_sender_confirmed_by_users",
        "facility_transfers", type_="foreignkey",
    )
    op.drop_column("facility_transfers", "receiver_confirmed_by")
    op.drop_column("facility_transfers", "receiver_confirmed_at")
    op.drop_column("facility_transfers", "sender_confirmed_by")
    op.drop_column("facility_transfers", "sender_confirmed_at")
