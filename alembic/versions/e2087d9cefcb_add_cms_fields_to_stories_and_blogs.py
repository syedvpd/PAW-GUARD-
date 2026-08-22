"""add_cms_fields_to_stories_and_blogs

Revision ID: e2087d9cefcb
Revises: p0q1r2s3t4u5
Create Date: 2026-08-22 19:16:38.784748

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2087d9cefcb'
down_revision: Union[str, None] = 'p0q1r2s3t4u5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to blog_posts
    op.add_column('blog_posts', sa.Column('tags', sa.String(length=255), nullable=True))
    op.add_column('blog_posts', sa.Column('author', sa.String(length=255), nullable=True))

    # Add columns to success_stories
    op.add_column('success_stories', sa.Column('slug', sa.String(length=255), nullable=True))
    op.add_column('success_stories', sa.Column('is_featured', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('success_stories', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))

    # Backfill slugs for existing success stories
    connection = op.get_bind()
    results = connection.execute(sa.text("SELECT id, title FROM success_stories WHERE slug IS NULL")).fetchall()
    import re
    for row in results:
        story_id, title = row[0], row[1]
        # Basic slugification
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        if not slug:
            slug = "story"
        # Append short UUID to guarantee uniqueness
        slug = f"{slug}-{str(story_id)[:8]}"
        connection.execute(
            sa.text("UPDATE success_stories SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": story_id}
        )

    # After backfilling, create unique index on slug
    op.create_index(op.f('ix_success_stories_slug'), 'success_stories', ['slug'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_success_stories_slug'), table_name='success_stories')
    op.drop_column('success_stories', 'sort_order')
    op.drop_column('success_stories', 'is_featured')
    op.drop_column('success_stories', 'slug')
    op.drop_column('blog_posts', 'author')
    op.drop_column('blog_posts', 'tags')
