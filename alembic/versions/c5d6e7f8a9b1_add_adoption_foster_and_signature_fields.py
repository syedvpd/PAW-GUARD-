"""add adoption foster-to-adopt and e-signature fields

Revision ID: c5d6e7f8a9b1
Revises: b3c4d5e6f7a9
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b1"
down_revision: Union[str, None] = "b3c4d5e6f7a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "adoption_applications",
        sa.Column(
            "is_foster_to_adopt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "adoption_applications",
        sa.Column("agreement_signed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "adoption_applications",
        sa.Column("agreement_signature_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("adoption_applications", "agreement_signature_name")
    op.drop_column("adoption_applications", "agreement_signed_at")
    op.drop_column("adoption_applications", "is_foster_to_adopt")
