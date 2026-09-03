"""add managed_facility_id to users table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-03 14:15:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '10s'")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS managed_facility_id UUID REFERENCES shelter_facilities(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_managed_facility_id ON users (managed_facility_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_managed_facility_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS managed_facility_id")
