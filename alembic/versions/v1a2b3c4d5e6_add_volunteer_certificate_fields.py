"""add_volunteer_certificate_fields

Adds is_certified, certificate_issued_at, and certificate_object_key to volunteer_profiles table.

Revision ID: v1a2b3c4d5e6
Revises: c4e5f6a7b8d9
Create Date: 2026-09-04 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "v1a2b3c4d5e6"
down_revision: Union[str, None] = "c4e5f6a7b8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("volunteer_profiles")}

    if "is_certified" not in existing_cols:
        op.add_column(
            "volunteer_profiles",
            sa.Column(
                "is_certified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "certificate_issued_at" not in existing_cols:
        op.add_column(
            "volunteer_profiles",
            sa.Column("certificate_issued_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "certificate_object_key" not in existing_cols:
        op.add_column(
            "volunteer_profiles",
            sa.Column("certificate_object_key", sa.String(length=1024), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("volunteer_profiles")}

    if "certificate_object_key" in existing_cols:
        op.drop_column("volunteer_profiles", "certificate_object_key")
    if "certificate_issued_at" in existing_cols:
        op.drop_column("volunteer_profiles", "certificate_issued_at")
    if "is_certified" in existing_cols:
        op.drop_column("volunteer_profiles", "is_certified")
