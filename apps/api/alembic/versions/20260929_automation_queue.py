"""Durable automation outbox and non-executing voice requests.

Revision ID: 20260929_auto
Revises: 43c41d2e6a3b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '20260929_auto'
down_revision = '43c41d2e6a3b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'automation_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('kind', sa.String(45), nullable=False),
        sa.Column('idempotency_key', sa.String(200), nullable=False, unique=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(35), nullable=False),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('result_data', postgresql.JSONB, nullable=False),
        sa.Column('attempt_count', sa.Integer, nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('last_error', sa.Text),
        sa.Column('external_id', sa.String(250)),
        sa.Column('requested_by', sa.String(120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_automation_claim', 'automation_jobs', ['status', 'next_attempt_at'])
    op.create_index('ix_automation_jobs_kind', 'automation_jobs', ['kind'])
    op.create_index('ix_automation_jobs_status', 'automation_jobs', ['status'])
    op.create_index('ix_automation_jobs_transaction_id', 'automation_jobs', ['transaction_id'])
    op.create_table(
        'voice_change_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('idempotency_key', sa.String(200), nullable=False, unique=True),
        sa.Column('request_type', sa.String(40), nullable=False),
        sa.Column('request_note', sa.Text, nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('external_call_id', sa.String(180), nullable=False),
        sa.Column('reviewed_by', sa.String(120)),
        sa.Column('review_note', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_voice_change_requests_transaction_id', 'voice_change_requests', ['transaction_id'])


def downgrade():
    op.drop_index('ix_voice_change_requests_transaction_id', table_name='voice_change_requests')
    op.drop_table('voice_change_requests')
    op.drop_index('ix_automation_jobs_transaction_id', table_name='automation_jobs')
    op.drop_index('ix_automation_jobs_status', table_name='automation_jobs')
    op.drop_index('ix_automation_jobs_kind', table_name='automation_jobs')
    op.drop_index('ix_automation_claim', table_name='automation_jobs')
    op.drop_table('automation_jobs')
