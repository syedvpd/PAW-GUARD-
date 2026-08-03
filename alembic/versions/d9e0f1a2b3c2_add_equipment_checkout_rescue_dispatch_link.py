"""add_equipment_checkout_rescue_dispatch_link

PRR 3.3: wire the fleet ledger to rescue dispatches. Equipment named on a
dispatch is auto-checked-out against the dispatch and auto-released when the
rescue completes (ADMITTED) or fails (REJECTED). Adds a nullable FK from
`equipment_checkouts.rescue_dispatch_id` to `rescue_dispatches.id`.

Revision ID: d9e0f1a2b3c2
Revises: d8e9f0a1b2c2
Create Date: 2026-08-03 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c2"
down_revision: str | None = "d8e9f0a1b2c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "equipment_checkouts",
        sa.Column("rescue_dispatch_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_equipment_checkouts_rescue_dispatch_id"),
        "equipment_checkouts", ["rescue_dispatch_id"], unique=False,
    )
    op.create_foreign_key(
        op.f("fk_equipment_checkouts_rescue_dispatch_id_rescue_dispatches"),
        "equipment_checkouts", "rescue_dispatches", ["rescue_dispatch_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_equipment_checkouts_rescue_dispatch_id_rescue_dispatches"),
        "equipment_checkouts", type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_equipment_checkouts_rescue_dispatch_id"),
        table_name="equipment_checkouts",
    )
    op.drop_column("equipment_checkouts", "rescue_dispatch_id")
