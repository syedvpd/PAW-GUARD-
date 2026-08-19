"""add notification governance tables

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-08-19 12:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'h4i5j6k7l8m9'
down_revision: Union[str, None] = 'g3h4i5j6k7l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. notification_global_config
    op.create_table(
        'notification_global_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('push_status', sa.String(16), nullable=False, server_default='ENABLED'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 2. notification_module_configs
    op.create_table(
        'notification_module_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('module_name', sa.String(64), nullable=False, unique=True),
        sa.Column('push_status', sa.String(16), nullable=False, server_default='ENABLED'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 3. notification_trigger_configs
    op.create_table(
        'notification_trigger_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('trigger_code', sa.String(64), nullable=False, unique=True),
        sa.Column('module_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(128), nullable=False),
        sa.Column('push_status', sa.String(16), nullable=False, server_default='ENABLED'),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('default_priority', sa.String(16), nullable=False, server_default='HIGH'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_notification_trigger_configs_module_name', 'notification_trigger_configs', ['module_name'])

    # 4. notification_approval_queue
    op.create_table(
        'notification_approval_queue',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('trigger_code', sa.String(64), nullable=False),
        sa.Column('module_name', sa.String(64), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('action_url', sa.String(512), nullable=True),
        sa.Column('image_url', sa.String(512), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('recipient_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('target_user_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('priority', sa.String(16), nullable=False, server_default='HIGH'),
        sa.Column('status', sa.String(32), nullable=False, server_default='PENDING_APPROVAL'),
        sa.Column('pause_reason', sa.Text(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('requested_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_notification_approval_queue_status', 'notification_approval_queue', ['status'])
    op.create_index('ix_notification_approval_queue_trigger_code', 'notification_approval_queue', ['trigger_code'])
    op.create_index('ix_notification_approval_queue_module_name', 'notification_approval_queue', ['module_name'])

    # 5. notification_governance_audit_logs
    op.create_table(
        'notification_governance_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('notification_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('notification_approval_queue.id', ondelete='SET NULL'), nullable=True),
        sa.Column('trigger_code', sa.String(64), nullable=False),
        sa.Column('module_name', sa.String(64), nullable=False),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('actor_role', sa.String(64), nullable=True),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('previous_status', sa.String(32), nullable=True),
        sa.Column('new_status', sa.String(32), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_notification_governance_audit_logs_action', 'notification_governance_audit_logs', ['action'])
    op.create_index('ix_notification_governance_audit_logs_trigger_code', 'notification_governance_audit_logs', ['trigger_code'])
    op.create_index('ix_notification_governance_audit_logs_module_name', 'notification_governance_audit_logs', ['module_name'])


def downgrade() -> None:
    op.drop_table('notification_governance_audit_logs')
    op.drop_table('notification_approval_queue')
    op.drop_table('notification_trigger_configs')
    op.drop_table('notification_module_configs')
    op.drop_table('notification_global_config')
