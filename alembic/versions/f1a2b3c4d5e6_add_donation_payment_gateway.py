"""add_donation_payment_gateway

Revision ID: f1a2b3c4d5e6
Revises: deac4a16c5fe, e7f9a2b1c3d0
Create Date: 2026-07-30 06:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = ("deac4a16c5fe", "e7f9a2b1c3d0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("donations", sa.Column("payment_provider", sa.String(length=32), nullable=True))
    op.add_column("donations", sa.Column("gateway_order_id", sa.String(length=128), nullable=True))
    op.add_column("donations", sa.Column("gateway_payment_id", sa.String(length=128), nullable=True))
    op.add_column("donations", sa.Column("gateway_signature", sa.String(length=512), nullable=True))
    op.create_unique_constraint(
        "uq_donations_gateway_order_id", "donations", ["gateway_order_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_donations_gateway_order_id", "donations", type_="unique")
    op.drop_column("donations", "gateway_signature")
    op.drop_column("donations", "gateway_payment_id")
    op.drop_column("donations", "gateway_order_id")
    op.drop_column("donations", "payment_provider")
