"""make_lost_found_broadcast_approval_optional

Revision ID: 2e288a4af48e
Revises: f00182391f58
Create Date: 2026-08-24 11:17:02.535705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2e288a4af48e'
down_revision: Union[str, None] = 'f00182391f58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE notification_trigger_configs SET requires_approval = FALSE WHERE trigger_code = 'lost_found_broadcast'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE notification_trigger_configs SET requires_approval = TRUE WHERE trigger_code = 'lost_found_broadcast'"
    )
