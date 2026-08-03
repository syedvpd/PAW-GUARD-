"""add_legal_documents_and_urgent_alerts

Revision ID: e2f4a6b8c0d2
Revises: b6c7d8e9f0a1
Create Date: 2026-08-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f4a6b8c0d2"
down_revision: str | None = "b6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pk_id() -> sa.Column:
    return sa.Column(
        "id",
        sa.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # ── Legal framework content ────────────────────────────────────────────

    op.create_table(
        "legal_documents",
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "document_type",
            sa.String(32),
            nullable=False,
            server_default="other",
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        _pk_id(),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_legal_documents")),
        sa.UniqueConstraint("slug", name=op.f("uq_legal_documents_slug")),
    )
    op.create_index(
        op.f("ix_legal_documents_slug"), "legal_documents", ["slug"], unique=True
    )
    op.create_index(
        op.f("ix_legal_documents_document_type"),
        "legal_documents",
        ["document_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_legal_documents_status"),
        "legal_documents",
        ["status"],
        unique=False,
    )

    # ── Urgent alert banner ────────────────────────────────────────────────

    op.create_table(
        "urgent_alerts",
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        _pk_id(),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_urgent_alerts")),
    )
    op.create_index(
        op.f("ix_urgent_alerts_severity"),
        "urgent_alerts",
        ["severity"],
        unique=False,
    )
    op.create_index(
        op.f("ix_urgent_alerts_is_active"),
        "urgent_alerts",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("urgent_alerts")
    op.drop_table("legal_documents")
