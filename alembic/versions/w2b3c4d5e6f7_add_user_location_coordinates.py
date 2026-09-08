"""add_user_location_coordinates

Adds nullable latitude/longitude to users so lost-pet alert broadcasts can be
scoped to a radius around the report instead of fanning out to every account.

Revision ID: w2b3c4d5e6f7
Revises: a6e7c70b4eb2
Create Date: 2026-09-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "w2b3c4d5e6f7"
down_revision: Union[str, None] = "a6e7c70b4eb2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("users")}

    if "latitude" not in existing_cols:
        op.add_column("users", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    if "longitude" not in existing_cols:
        op.add_column("users", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("users")}

    if "longitude" in existing_cols:
        op.drop_column("users", "longitude")
    if "latitude" in existing_cols:
        op.drop_column("users", "latitude")
