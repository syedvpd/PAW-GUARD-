"""add_rescue_media_evidence

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a3
Create Date: 2026-08-02 16:30:00.000000

Adds `media_evidence` (JSONB, PRR 3.2 intake media evidence: up to 5 photos +
short video clips from the public wizard, stored as confirmed storage object
keys) to `rescue_requests`. Existing rows get NULL - the field is optional on
intake, so no backfill is needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rescue_requests",
        sa.Column(
            "media_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("rescue_requests", "media_evidence")
