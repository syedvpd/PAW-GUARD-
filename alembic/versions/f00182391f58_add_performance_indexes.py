"""add_performance_indexes

Revision ID: f00182391f58
Revises: e2087d9cefcb
Create Date: 2026-08-23 19:58:07.051367

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f00182391f58'
down_revision: Union[str, None] = 'e2087d9cefcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_success_stories_status_published_at',
        'success_stories',
        ['status', 'published_at']
    )
    op.create_index(
        'ix_blog_posts_status_published_at',
        'blog_posts',
        ['status', 'published_at']
    )
    op.create_index(
        'ix_veterinary_partners_is_active_is_emergency',
        'veterinary_partners',
        ['is_active', 'is_emergency']
    )


def downgrade() -> None:
    op.drop_index('ix_success_stories_status_published_at', table_name='success_stories')
    op.drop_index('ix_blog_posts_status_published_at', table_name='blog_posts')
    op.drop_index('ix_veterinary_partners_is_active_is_emergency', table_name='veterinary_partners')

