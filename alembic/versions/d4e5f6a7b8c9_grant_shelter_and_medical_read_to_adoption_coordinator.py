"""grant shelter:read and medical:read to adoption_coordinator role

Revision ID: d4e5f6a7b8c9
Revises: b9c0d1e2f3a4
Create Date: 2026-08-19 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "b9c0d1e2f3a4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

PERMISSIONS = [
    ("shelter:read", "View shelter facilities, kennels, and dog timelines"),
    ("medical:read", "View clinical examination history and medical adoption clearances"),
]


def upgrade() -> None:
    # 1. Ensure permissions exist
    for code, desc in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, code, description, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :code, :desc, now(), now()) "
                "ON CONFLICT (code) DO NOTHING;"
            ).bindparams(code=code, desc=desc)
        )

    # 2. Grant permissions to adoption_coordinator role
    for code, _ in PERMISSIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM roles r, permissions p
                WHERE r.name = 'adoption_coordinator'
                  AND p.code = :code
                ON CONFLICT DO NOTHING;
                """
            ).bindparams(code=code)
        )


def downgrade() -> None:
    for code, _ in PERMISSIONS:
        op.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                WHERE role_id = (SELECT id FROM roles WHERE name = 'adoption_coordinator')
                  AND permission_id = (SELECT id FROM permissions WHERE code = :code);
                """
            ).bindparams(code=code)
        )
