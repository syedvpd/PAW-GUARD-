"""rbac: system:admin belongs to super_admin only (PRR 2.1, GAP-0)

Revision ID: j8e9f0a1b2c3
Revises: i7d8e9f0a1b2
"""

from collections.abc import Sequence

from alembic import op

revision: str = "j8e9f0a1b2c3"
down_revision: str | None = "i7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id = (SELECT id FROM permissions WHERE code = 'system:admin')
          AND role_id NOT IN (SELECT id FROM roles WHERE name = 'super_admin')
        """
    )
    op.execute(
        """
        DELETE FROM user_permissions
        WHERE permission_id = (SELECT id FROM permissions WHERE code = 'system:admin')
          AND user_id NOT IN (
              SELECT ur.user_id FROM user_roles ur
              JOIN roles r ON r.id = ur.role_id
              WHERE r.name = 'super_admin'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, (SELECT id FROM permissions WHERE code = 'system:admin')
        FROM roles r
        WHERE r.name = 'rescue_centre_admin'
          AND (SELECT id FROM permissions WHERE code = 'system:admin') IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = (SELECT id FROM permissions WHERE code = 'system:admin')
          )
        """
    )
