"""grant companion_pet permissions to app_user and general_public roles

Revision ID: c1d2e3f4a5b6
Revises: a2b3c4d5e6f7
Create Date: 2026-08-12 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

PERMISSIONS = [
    ("public:read", "public:read"),
    ("public:create", "public:create"),
    ("companion_pet:create", "companion_pet:create"),
    ("companion_pet:read", "companion_pet:read"),
    ("companion_pet:update", "companion_pet:update"),
    ("companion_pet:delete", "companion_pet:delete"),
    ("companion_pet:medical_upload", "companion_pet:medical_upload"),
    ("safety_tag:manage", "safety_tag:manage"),
    ("vet_clinic:read", "vet_clinic:read"),
    ("appointment:create", "appointment:create"),
    ("appointment:read", "appointment:read"),
    ("appointment:cancel", "appointment:cancel"),
    ("lost_found:broadcast", "lost_found:broadcast"),
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

    # 2. Ensure app_user role exists
    op.execute(
        """
        INSERT INTO roles (id, name, description, is_system, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'app_user',
            'Public application user for companion pets, lost & found, and emergency reporting.',
            false,
            now(),
            now()
        )
        ON CONFLICT (name) DO NOTHING;
        """
    )

    # 3. Grant permissions to app_user and general_public
    for target_role in ("app_user", "general_public"):
        for code, _ in PERMISSIONS:
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id "
                    "FROM roles r, permissions p "
                    "WHERE r.name = :role_name AND p.code = :code "
                    "ON CONFLICT DO NOTHING;"
                ).bindparams(role_name=target_role, code=code)
            )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE name = 'app_user')
          AND permission_id IN (
              SELECT id FROM permissions WHERE code IN (
                  'companion_pet:create', 'companion_pet:read', 'companion_pet:update',
                  'companion_pet:delete', 'companion_pet:medical_upload'
              )
          );
        """
    )
