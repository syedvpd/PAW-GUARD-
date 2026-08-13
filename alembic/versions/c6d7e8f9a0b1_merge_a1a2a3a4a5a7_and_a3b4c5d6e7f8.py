"""merge_heads

Merge the applied audit branch head (a1a2a3a4a5a7) with the previously
unapplied fork head (a3b4c5d6e7f8) to collapse the repository to a single
Alembic head.

Revision ID: c6d7e8f9a0b1
Revises: a1a2a3a4a5a7, a3b4c5d6e7f8
Create Date: 2026-08-13 22:10:00.000000

"""

from collections.abc import Sequence

revision: str = "c6d7e8f9a0b1"
down_revision: tuple[str, ...] | None = ("a1a2a3a4a5a7", "a3b4c5d6e7f8")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
