"""revoke donation:read from public donor role

Security fix (C-1): the `donor` role was seeded with `donation:read`, a
staff-level permission that (a) let any donor download ANY donor's receipt
through the receipt endpoint's permission fallback and (b) exposed the
staff listing endpoints (GET /donations, /donations/donors,
/donations/sponsorships) to every registered donor.

Donors reach their own data through the user-scoped endpoints
(/donations/history, /donations/sponsorships/my) and the ownership check on
the receipt endpoint, none of which require `donation:read`.

Revision ID: b6c7d8e9f0a1
Revises: a1b2c3d4e5f6
Create Date: 2026-08-01 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE name = 'donor')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'donation:read')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'donor' AND p.code = 'donation:read'
        ON CONFLICT DO NOTHING
        """
    )
