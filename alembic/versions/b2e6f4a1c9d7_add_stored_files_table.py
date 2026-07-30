"""add_stored_files_table

The StoredFile ORM model (src/pawguard/modules/storage/models.py) and the
storage/upload endpoints have existed since the storage module build, but no
migration ever created the backing table, and alembic/env.py never imported
the module's models, so autogenerate couldn't see it either — any code path
touching stored_files (e.g. confirming an upload) fails with
`relation "stored_files" does not exist`.

Revision ID: b2e6f4a1c9d7
Revises: a7c9e4f2b8d1
Create Date: 2026-07-30 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2e6f4a1c9d7"
down_revision: Union[str, None] = "a7c9e4f2b8d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("folder", sa.String(length=64), nullable=False),
        sa.Column("is_uploaded", sa.Boolean(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_stored_files_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_files")),
    )
    op.create_index(op.f("ix_stored_files_user_id"), "stored_files", ["user_id"], unique=False)
    op.create_index(op.f("ix_stored_files_object_key"), "stored_files", ["object_key"], unique=True)
    op.create_index(op.f("ix_stored_files_folder"), "stored_files", ["folder"], unique=False)
    op.create_index(op.f("ix_stored_files_entity_type"), "stored_files", ["entity_type"], unique=False)
    op.create_index(op.f("ix_stored_files_entity_id"), "stored_files", ["entity_id"], unique=False)
    op.create_index(
        "ix_stored_files_entity", "stored_files", ["entity_type", "entity_id"], unique=False
    )
    op.create_index(
        "ix_stored_files_folder_uploaded", "stored_files", ["folder", "uploaded_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_stored_files_folder_uploaded", table_name="stored_files")
    op.drop_index("ix_stored_files_entity", table_name="stored_files")
    op.drop_index(op.f("ix_stored_files_entity_id"), table_name="stored_files")
    op.drop_index(op.f("ix_stored_files_entity_type"), table_name="stored_files")
    op.drop_index(op.f("ix_stored_files_folder"), table_name="stored_files")
    op.drop_index(op.f("ix_stored_files_object_key"), table_name="stored_files")
    op.drop_index(op.f("ix_stored_files_user_id"), table_name="stored_files")
    op.drop_table("stored_files")
