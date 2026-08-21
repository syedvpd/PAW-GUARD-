"""add_lost_found_photo_object_key

Revision ID: p0q1r2s3t4u5
Revises: n9o0p1q2r3s4
Create Date: 2026-08-21 12:00:00.000000

Adds a permanent `photo_object_key` column to `lost_reports` and
`found_reports`. This stores the stable S3/Supabase object reference for an
uploaded pet photo (the same storage principle used by the Emergency / rescue
`media_evidence` flow) instead of a time-limited presigned download URL.

The pre-existing `photo_url` column is retained for backward compatibility with
legacy reports that reference externally-hosted image URLs; it is no longer
written by the upload flow, which now stores only the object key and resolves
a fresh signed URL on every read.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p0q1r2s3t4u5"
down_revision: str | None = "n9o0p1q2r3s4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lost_reports",
        sa.Column("photo_object_key", sa.String(512), nullable=True),
    )
    op.add_column(
        "found_reports",
        sa.Column("photo_object_key", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("found_reports", "photo_object_key")
    op.drop_column("lost_reports", "photo_object_key")
