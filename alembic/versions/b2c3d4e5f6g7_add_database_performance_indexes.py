"""add database performance indexes for slow queries and admin dashboards

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-25 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6g7"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Notifications user & deleted filter (fixes high-frequency unread/count queries)
    op.create_index(
        "idx_notifications_user_deleted",
        "notifications",
        ["user_id", "deleted_at"],
        unique=False,
    )

    # 2. RBAC permission & user role checks (runs on EVERY authenticated HTTP request)
    op.create_index(
        "idx_role_permissions_role_perm",
        "role_permissions",
        ["role_id", "permission_id"],
        unique=False,
    )
    op.create_index(
        "idx_user_roles_user_role",
        "user_roles",
        ["user_id", "role_id"],
        unique=False,
    )

    # 3. Audit log reverse chronological queries (used by admin audit views)
    op.create_index(
        "idx_auth_audit_logs_created_at_desc",
        "auth_audit_logs",
        [sa.text("created_at DESC")],
        unique=False,
    )

    # 4. Outbox events status & priority queue polling
    op.create_index(
        "idx_outbox_events_status_created",
        "outbox_events",
        ["status", "created_at"],
        unique=False,
    )

    # 5. Users table lookup & auth filtering
    op.create_index(
        "idx_users_email_deleted",
        "users",
        ["email", "deleted_at"],
        unique=False,
    )

    # 6. Dog profiles search & listing (admin & public search queries)
    op.create_index(
        "idx_dog_profiles_search_name_status",
        "dog_profiles",
        ["deleted_at", "status", "name"],
        unique=False,
    )

    # 7. Rescue requests ticket & phone fast lookup
    op.create_index(
        "idx_rescue_requests_ticket_phone",
        "rescue_requests",
        ["ticket_number", "reporter_phone"],
        unique=False,
    )

    # 8. Adoption applications dashboard & user filter
    op.create_index(
        "idx_adoption_apps_status_deleted",
        "adoption_applications",
        ["deleted_at", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_adoption_apps_status_deleted", table_name="adoption_applications")
    op.drop_index("idx_rescue_requests_ticket_phone", table_name="rescue_requests")
    op.drop_index("idx_dog_profiles_search_name_status", table_name="dog_profiles")
    op.drop_index("idx_users_email_deleted", table_name="users")
    op.drop_index("idx_outbox_events_status_created", table_name="outbox_events")
    op.drop_index("idx_auth_audit_logs_created_at_desc", table_name="auth_audit_logs")
    op.drop_index("idx_user_roles_user_role", table_name="user_roles")
    op.drop_index("idx_role_permissions_role_perm", table_name="role_permissions")
    op.drop_index("idx_notifications_user_deleted", table_name="notifications")
