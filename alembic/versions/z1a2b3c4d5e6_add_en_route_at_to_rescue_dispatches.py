"""add en_route_at to rescue_dispatches

Revision ID: z1a2b3c4d5e6
Revises: x1y2z3a4b5c6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z1a2b3c4d5e6"
down_revision: Union[str, None] = "x1y2z3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rescue_dispatches",
        sa.Column("en_route_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rescue_dispatches", "en_route_at")
