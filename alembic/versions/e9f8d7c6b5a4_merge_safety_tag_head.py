"""merge safety tag head and c6d7e8f9a0b1

Revision ID: e9f8d7c6b5a4
Revises: b3c4d5e6f7g8, c6d7e8f9a0b1
Create Date: 2026-08-15 14:35:00.000000

"""
from collections.abc import Sequence

revision: str = "e9f8d7c6b5a4"
down_revision: Sequence[str] = ("b3c4d5e6f7g8", "c6d7e8f9a0b1")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
