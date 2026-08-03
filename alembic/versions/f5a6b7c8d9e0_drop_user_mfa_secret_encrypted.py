"""drop_user_mfa_secret_encrypted

Revision ID: f5a6b7c8d9e0
Revises: f3a0b1c2d3e4
Create Date: 2026-08-02 18:45:00.000000

Removes the legacy `mfa_secret_encrypted` column from `users`. MFA secrets
have always been stored in the `mfa_devices.secret_encrypted` column; this
`users` column was never written or read by any runtime code since the
multi-device MFA model landed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "f3a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "mfa_secret_encrypted")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True),
    )
