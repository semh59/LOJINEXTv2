"""Outbox canonical fields: aggregate_version, claim_token, claimed_by_worker.

Revision ID: 011_outbox_canonical_fields
Revises: 010_security_hardening
Create Date: 2026-04-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011_outbox_canonical_fields"
down_revision = "010_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "identity_outbox",
        sa.Column(
            "aggregate_version", sa.Integer(), nullable=False, server_default="1"
        ),
    )

    op.add_column(
        "identity_outbox",
        sa.Column("claim_token", sa.String(50), nullable=True),
    )

    op.add_column(
        "identity_outbox",
        sa.Column("claimed_by_worker", sa.String(50), nullable=True),
    )

    op.alter_column(
        "identity_outbox",
        "retry_count",
        new_column_name="attempt_count",
    )

    op.alter_column(
        "identity_outbox",
        "last_error",
        new_column_name="last_error_code",
        type_=sa.String(100),
    )

    op.alter_column(
        "identity_outbox",
        "payload_json",
        type_=sa.Text(),
        postgresql_using="payload_json::text",
    )


def downgrade() -> None:
    op.alter_column(
        "identity_outbox",
        "payload_json",
        type_=sa.dialects.postgresql.JSONB(),
        postgresql_using="payload_json::jsonb",
    )

    op.alter_column(
        "identity_outbox",
        "last_error_code",
        new_column_name="last_error",
        type_=sa.Text(),
    )

    op.alter_column(
        "identity_outbox",
        "attempt_count",
        new_column_name="retry_count",
    )

    op.drop_column("identity_outbox", "claimed_by_worker")
    op.drop_column("identity_outbox", "claim_token")
    op.drop_column("identity_outbox", "aggregate_version")
