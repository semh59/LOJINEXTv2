"""Location outbox canonical fields: aggregate_type, aggregate_id, aggregate_version, claim_token, claimed_by_worker.

Revision ID: d1e2f3a4b5c6
Revises: b3c4d5e6f7a8
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "location_outbox",
        sa.Column("aggregate_type", sa.String(16), nullable=False, server_default="LOCATION"),
    )

    op.add_column(
        "location_outbox",
        sa.Column("aggregate_id", sa.String(26), nullable=False, server_default=""),
    )

    op.add_column(
        "location_outbox",
        sa.Column("aggregate_version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.add_column(
        "location_outbox",
        sa.Column("claim_token", sa.String(50), nullable=True),
    )

    op.add_column(
        "location_outbox",
        sa.Column("claimed_by_worker", sa.String(50), nullable=True),
    )

    op.alter_column(
        "location_outbox",
        "retry_count",
        new_column_name="attempt_count",
    )

    op.alter_column(
        "location_outbox",
        "payload_json",
        type_=sa.Text(),
        postgresql_using="payload_json::text",
    )

    op.create_index(
        "ix_location_outbox_aggregate",
        "location_outbox",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_location_outbox_aggregate", table_name="location_outbox")

    op.alter_column(
        "location_outbox",
        "payload_json",
        type_=sa.dialects.postgresql.JSONB(),
        postgresql_using="payload_json::jsonb",
    )

    op.alter_column(
        "location_outbox",
        "attempt_count",
        new_column_name="retry_count",
    )

    op.drop_column("location_outbox", "claimed_by_worker")
    op.drop_column("location_outbox", "claim_token")
    op.drop_column("location_outbox", "aggregate_version")
    op.drop_column("location_outbox", "aggregate_id")
    op.drop_column("location_outbox", "aggregate_type")
