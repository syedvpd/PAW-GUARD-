"""add check constraints to inventory donations sponsorships and financial transactions

Revision ID: 6da1e36044c4
Revises: b34424e4e94c
Create Date: 2026-08-01 22:56:44.735991

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6da1e36044c4'
down_revision: Union[str, None] = 'b34424e4e94c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("inventory_items", "ck_inventory_items_quantity_non_negative", "quantity >= 0"),
    ("inventory_items", "ck_inventory_items_unit_cost_non_negative", "unit_cost >= 0"),
    ("donations", "ck_donations_amount_positive", "amount > 0"),
    ("dog_sponsorships", "ck_dog_sponsorships_monthly_amount_positive", "monthly_amount > 0"),
    ("financial_transactions", "ck_financial_transactions_amount_positive", "amount > 0"),
)


def _assert_no_violations() -> None:
    """Refuse to apply a CHECK if existing rows already violate it.

    Existing bad data must be cleaned up deliberately before the constraint
    lands; silently skipping or guessing a repair would hide data problems.
    """
    bind = op.get_bind()
    for table, name, expression in _CONSTRAINTS:
        rows = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE NOT ({expression})")).scalar()
        if rows:
            raise RuntimeError(
                f"Refusing to add {name}: {rows} row(s) in {table} violate ({expression}). "
                "Clean the data first, then re-run this migration."
            )


def upgrade() -> None:
    _assert_no_violations()
    for table, name, expression in _CONSTRAINTS:
        op.create_check_constraint(name, table, expression)


def downgrade() -> None:
    for table, name, _expression in _CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
