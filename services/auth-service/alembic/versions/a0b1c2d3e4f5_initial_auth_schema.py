"""Initial auth schema

Revision ID: a0b1c2d3e4f5
Revises: 
Create Date: 2026-04-13 15:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # auth_credentials table
    op.create_table('auth_credentials',
        sa.Column('id', sa.String(length=26), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_auth_credentials_id'), 'auth_credentials', ['id'], unique=False)
    op.create_index(op.f('ix_auth_credentials_email'), 'auth_credentials', ['email'], unique=True)

    # auth_outbox table
    op.create_table('auth_outbox',
        sa.Column('outbox_id', sa.String(length=26), nullable=False),
        sa.Column('aggregate_type', sa.String(length=32), nullable=False),
        sa.Column('aggregate_id', sa.String(length=64), nullable=False),
        sa.Column('aggregate_version', sa.Integer(), nullable=False),
        sa.Column('event_name', sa.String(length=128), nullable=False),
        sa.Column('event_version', sa.Integer(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('partition_key', sa.String(length=100), nullable=False),
        sa.Column('correlation_id', sa.String(length=64), nullable=True),
        sa.Column('causation_id', sa.String(length=64), nullable=True),
        sa.Column('publish_status', sa.String(length=20), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('last_error_code', sa.String(length=100), nullable=True),
        sa.Column('claim_token', sa.String(length=50), nullable=True),
        sa.Column('claimed_by_worker', sa.String(length=50), nullable=True),
        sa.Column('created_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('next_attempt_at_utc', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claim_expires_at_utc', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at_utc', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('outbox_id')
    )
    op.create_index(op.f('ix_auth_outbox_correlation_id'), 'auth_outbox', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_auth_outbox_causation_id'), 'auth_outbox', ['causation_id'], unique=False)
    op.create_index('ix_auth_outbox_status_attempt_created', 'auth_outbox', ['publish_status', 'next_attempt_at_utc', 'created_at_utc'], unique=False)
    op.create_index('ix_auth_outbox_aggregate', 'auth_outbox', ['aggregate_type', 'aggregate_id', 'created_at_utc'], unique=False)
    op.create_index('ix_auth_outbox_event_name', 'auth_outbox', ['event_name', 'created_at_utc'], unique=False)
    op.create_index('ix_auth_outbox_claim_expires', 'auth_outbox', ['claim_expires_at_utc'], unique=False)
    op.create_index('ix_auth_outbox_partition', 'auth_outbox', ['partition_key', 'publish_status', 'created_at_utc'], unique=False)

    # auth_worker_heartbeats table
    op.create_table('auth_worker_heartbeats',
        sa.Column('worker_name', sa.String(length=64), nullable=False),
        sa.Column('last_seen_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('worker_name')
    )

    op.create_table('auth_refresh_tokens',
        sa.Column('token_id', sa.String(length=26), nullable=False),
        sa.Column('user_id', sa.String(length=26), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('family_id', sa.String(length=26), nullable=False),
        sa.Column('expires_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at_utc', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('token_id'),
        sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_auth_refresh_tokens_family_id'), 'auth_refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_auth_refresh_tokens_token_hash'), 'auth_refresh_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_auth_refresh_tokens_user_id'), 'auth_refresh_tokens', ['user_id'], unique=False)

    op.create_table('auth_signing_keys',
        sa.Column('kid', sa.String(length=26), nullable=False),
        sa.Column('algorithm', sa.String(length=50), nullable=False),
        sa.Column('public_key_pem', sa.String(), nullable=False),
        sa.Column('private_key_ciphertext_b64', sa.String(), nullable=False),
        sa.Column('private_key_kek_version', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retired_at_utc', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('kid')
    )

    op.create_table('auth_service_clients',
        sa.Column('client_id', sa.String(length=255), nullable=False),
        sa.Column('service_name', sa.String(length=255), nullable=False),
        sa.Column('client_secret_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('rotated_at_utc', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('client_id'),
        sa.UniqueConstraint('service_name')
    )

    # auth_audit_log table
    op.create_table('auth_audit_log',
        sa.Column('audit_id', sa.String(length=26), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.String(length=64), nullable=False),
        sa.Column('action_type', sa.String(length=32), nullable=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False),
        sa.Column('actor_role', sa.String(length=32), nullable=False),
        sa.Column('old_snapshot_json', sa.Text(), nullable=True),
        sa.Column('new_snapshot_json', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('audit_id')
    )
    op.create_index('ix_auth_audit_log_target', 'auth_audit_log', ['target_type', 'target_id', 'created_at_utc'], unique=False)
    op.create_index('ix_auth_audit_log_actor', 'auth_audit_log', ['actor_id', 'created_at_utc'], unique=False)
    op.create_index('ix_auth_audit_log_action', 'auth_audit_log', ['action_type', 'created_at_utc'], unique=False)

def downgrade() -> None:
    op.drop_table('auth_audit_log')
    op.drop_table('auth_service_clients')
    op.drop_table('auth_signing_keys')
    op.drop_index(op.f('ix_auth_refresh_tokens_user_id'), table_name='auth_refresh_tokens')
    op.drop_index(op.f('ix_auth_refresh_tokens_token_hash'), table_name='auth_refresh_tokens')
    op.drop_index(op.f('ix_auth_refresh_tokens_family_id'), table_name='auth_refresh_tokens')
    op.drop_table('auth_refresh_tokens')
    op.drop_table('auth_worker_heartbeats')
    op.drop_index('ix_auth_outbox_partition', table_name='auth_outbox')
    op.drop_index('ix_auth_outbox_claim_expires', table_name='auth_outbox')
    op.drop_index('ix_auth_outbox_event_name', table_name='auth_outbox')
    op.drop_index('ix_auth_outbox_aggregate', table_name='auth_outbox')
    op.drop_index('ix_auth_outbox_status_attempt_created', table_name='auth_outbox')
    op.drop_index(op.f('ix_auth_outbox_causation_id'), table_name='auth_outbox')
    op.drop_index(op.f('ix_auth_outbox_correlation_id'), table_name='auth_outbox')
    op.drop_table('auth_outbox')

    op.drop_index(op.f('ix_auth_credentials_email'), table_name='auth_credentials')
    op.drop_index(op.f('ix_auth_credentials_id'), table_name='auth_credentials')
    op.drop_table('auth_credentials')
