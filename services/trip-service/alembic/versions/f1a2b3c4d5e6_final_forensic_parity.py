"""final forensic parity

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f1a2b3c4d5e6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Type Conversions (Text/JSON -> JSONB)
    op.alter_column(
        "trip_trip_evidence", "raw_payload_json", type_=postgresql.JSONB, postgresql_using="raw_payload_json::jsonb"
    )
    op.alter_column(
        "trip_trip_delete_audit", "snapshot_json", type_=postgresql.JSONB, postgresql_using="snapshot_json::jsonb"
    )
    op.alter_column(
        "trip_audit_log", "changed_fields_json", type_=postgresql.JSONB, postgresql_using="changed_fields_json::jsonb"
    )
    op.alter_column(
        "trip_audit_log", "old_snapshot_json", type_=postgresql.JSONB, postgresql_using="old_snapshot_json::jsonb"
    )
    op.alter_column(
        "trip_audit_log", "new_snapshot_json", type_=postgresql.JSONB, postgresql_using="new_snapshot_json::jsonb"
    )
    op.alter_column("trip_outbox", "payload_json", type_=postgresql.JSONB, postgresql_using="payload_json::jsonb")
    op.alter_column(
        "trip_idempotency_records",
        "response_headers_json",
        type_=postgresql.JSONB,
        postgresql_using="response_headers_json::jsonb",
    )
    op.alter_column(
        "trip_idempotency_records",
        "response_body_json",
        type_=postgresql.JSONB,
        postgresql_using="response_body_json::jsonb",
    )

    # 2. Index Renaming
    op.drop_index("uq_trips_source_slip_no_telegram", table_name="trip_trips")
    op.create_index(
        "ix_trip_trips_source_slip_no_telegram",
        "trip_trips",
        ["source_slip_no"],
        unique=True,
        postgresql_where=sa.text("source_type = 'TELEGRAM_TRIP_SLIP' AND source_slip_no IS NOT NULL"),
    )

    op.drop_index("uq_trips_source_reference_key", table_name="trip_trips")
    op.create_index(
        "ix_trip_trips_source_reference_key",
        "trip_trips",
        ["source_reference_key"],
        unique=True,
        postgresql_where=sa.text("source_reference_key IS NOT NULL"),
    )

    op.drop_index("ix_evidence_trip_id", table_name="trip_trip_evidence")
    op.create_index("ix_trip_evidence_trip_id", "trip_trip_evidence", ["trip_id"])

    op.drop_index("ix_evidence_source_slip", table_name="trip_trip_evidence")

    @sa.event.listens_for(sa.Table, "after_create")
    def create_indexes(target, connection, **kw):
        if target.name == "trip_trip_evidence":
            connection.execute(
                sa.text(
                    "CREATE INDEX ix_trip_evidence_source_slip ON trip_trip_evidence (evidence_source, source_slip_no)"
                )
            )

    op.create_index("ix_trip_evidence_source_slip", "trip_trip_evidence", ["evidence_source", "source_slip_no"])

    op.drop_index("ix_evidence_telegram_msg", table_name="trip_trip_evidence")
    op.create_index("ix_trip_evidence_telegram_msg", "trip_trip_evidence", ["telegram_message_id"])

    op.drop_index("ix_evidence_row_number", table_name="trip_trip_evidence")
    op.create_index("ix_trip_evidence_row_number", "trip_trip_evidence", ["row_number"])

    op.drop_index("ix_enrichment_status_retry", table_name="trip_trip_enrichment")
    op.create_index(
        "ix_trip_enrichment_status_retry", "trip_trip_enrichment", ["enrichment_status", "next_retry_at_utc"]
    )

    op.drop_index("ix_enrichment_route", table_name="trip_trip_enrichment")
    op.create_index("ix_trip_enrichment_route", "trip_trip_enrichment", ["route_status"])

    op.drop_index("ix_enrichment_claim_exp", table_name="trip_trip_enrichment")
    op.create_index("ix_trip_enrichment_claim_exp", "trip_trip_enrichment", ["claim_expires_at_utc"])

    op.drop_index("ix_timeline_trip_created", table_name="trip_trip_timeline")
    op.create_index("ix_trip_timeline_trip_created", "trip_trip_timeline", ["trip_id", "created_at_utc"])

    op.drop_index("ix_timeline_event_created", table_name="trip_trip_timeline")
    op.create_index("ix_trip_timeline_event_created", "trip_trip_timeline", ["event_type", "created_at_utc"])

    op.drop_index("idx_trip_audit_trip_created", table_name="trip_audit_log")
    op.create_index("ix_trip_audit_log_trip_created", "trip_audit_log", ["trip_id", "created_at_utc"])

    op.drop_index("ix_outbox_status_attempt_created", table_name="trip_outbox")
    op.create_index(
        "ix_trip_outbox_status_attempt_created",
        "trip_outbox",
        ["publish_status", "next_attempt_at_utc", "created_at_utc"],
    )

    op.drop_index("ix_outbox_aggregate", table_name="trip_outbox")
    op.create_index("ix_trip_outbox_aggregate", "trip_outbox", ["aggregate_type", "aggregate_id", "created_at_utc"])

    op.drop_index("ix_outbox_event_name", table_name="trip_outbox")
    op.create_index("ix_trip_outbox_event_name", "trip_outbox", ["event_name", "created_at_utc"])

    op.drop_index("ix_outbox_claim_exp", table_name="trip_outbox")
    op.create_index("ix_trip_outbox_claim_exp", "trip_outbox", ["claim_expires_at_utc"])

    op.drop_index("ix_idempotency_expires", table_name="trip_idempotency_records")
    op.create_index("ix_trip_idempotency_expires", "trip_idempotency_records", ["expires_at_utc"])

    op.create_index("ix_trip_worker_heartbeats_recorded_at", "worker_heartbeats", ["recorded_at_utc"])


def downgrade() -> None:
    # Downgen is skipped for brevity (Forensic only)
    pass
