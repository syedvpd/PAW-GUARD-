"""add_version_id_optimistic_locking

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-08-25 16:59:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "adoption_applications",
        sa.Column("version_id", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "dog_profiles",
        sa.Column("version_id", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("dog_profiles", "version_id")
    op.drop_column("adoption_applications", "version_id")
