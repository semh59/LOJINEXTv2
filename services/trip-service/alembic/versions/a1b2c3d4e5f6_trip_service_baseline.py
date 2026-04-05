"""trip_service_baseline

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-03-27 19:45:00
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_COMPLETE_TRIP_SQL = """
vehicle_id IS NOT NULL AND
route_pair_id IS NOT NULL AND
route_id IS NOT NULL AND
origin_location_id IS NOT NULL AND
origin_name_snapshot IS NOT NULL AND
destination_location_id IS NOT NULL AND
destination_name_snapshot IS NOT NULL AND
tare_weight_kg IS NOT NULL AND
gross_weight_kg IS NOT NULL AND
net_weight_kg IS NOT NULL AND
planned_duration_s IS NOT NULL AND
planned_end_utc IS NOT NULL
"""


def upgrade() -> None:
    op.create_table(
        "trip_idempotency_records",
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("endpoint_fingerprint", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_headers_json", sa.JSON(), nullable=False),
        sa.Column("response_body_json", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_key", "endpoint_fingerprint"),
    )
    op.create_index("ix_idempotency_expires", "trip_idempotency_records", ["expires_at_utc"], unique=False)

    op.create_table(
        "trip_outbox",
        sa.Column("event_id", sa.String(length=26), nullable=False),
        sa.Column("aggregate_type", sa.String(length=10), nullable=False),
        sa.Column("aggregate_id", sa.String(length=26), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=50), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("partition_key", sa.String(length=26), nullable=False),
        sa.Column("publish_status", sa.String(length=15), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_outbox_status_attempt_created",
        "trip_outbox",
        ["publish_status", "next_attempt_at_utc", "created_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_aggregate", "trip_outbox", ["aggregate_type", "aggregate_id", "created_at_utc"], unique=False
    )
    op.create_index("ix_outbox_event_name", "trip_outbox", ["event_name", "created_at_utc"], unique=False)

    op.create_table(
        "trip_trips",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("trip_no", sa.String(length=100), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_slip_no", sa.String(length=100), nullable=True),
        sa.Column("source_reference_key", sa.String(length=200), nullable=True),
        sa.Column("source_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("review_reason_code", sa.String(length=50), nullable=True),
        sa.Column("base_trip_id", sa.String(length=26), nullable=True),
        sa.Column("driver_id", sa.String(length=50), nullable=False),
        sa.Column("vehicle_id", sa.String(length=50), nullable=True),
        sa.Column("trailer_id", sa.String(length=50), nullable=True),
        sa.Column("route_pair_id", sa.String(length=50), nullable=True),
        sa.Column("route_id", sa.String(length=50), nullable=True),
        sa.Column("origin_location_id", sa.String(length=50), nullable=True),
        sa.Column("origin_name_snapshot", sa.String(length=200), nullable=True),
        sa.Column("destination_location_id", sa.String(length=50), nullable=True),
        sa.Column("destination_name_snapshot", sa.String(length=200), nullable=True),
        sa.Column("trip_datetime_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trip_timezone", sa.String(length=50), nullable=False),
        sa.Column("planned_duration_s", sa.Integer(), nullable=True),
        sa.Column("planned_end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tare_weight_kg", sa.Integer(), nullable=True),
        sa.Column("gross_weight_kg", sa.Integer(), nullable=True),
        sa.Column("net_weight_kg", sa.Integer(), nullable=True),
        sa.Column("is_empty_return", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_actor_type", sa.String(length=20), nullable=False),
        sa.Column("created_by_actor_id", sa.String(length=50), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("soft_deleted_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("soft_deleted_by_actor_id", sa.String(length=50), nullable=True),
        sa.CheckConstraint(
            "planned_duration_s IS NULL OR planned_duration_s >= 0", name="ck_trips_duration_non_negative"
        ),
        sa.CheckConstraint("tare_weight_kg IS NULL OR tare_weight_kg >= 0", name="ck_trips_tare_positive"),
        sa.CheckConstraint("gross_weight_kg IS NULL OR gross_weight_kg >= 0", name="ck_trips_gross_positive"),
        sa.CheckConstraint("net_weight_kg IS NULL OR net_weight_kg >= 0", name="ck_trips_net_positive"),
        sa.CheckConstraint(
            "gross_weight_kg IS NULL OR tare_weight_kg IS NULL OR gross_weight_kg >= tare_weight_kg",
            name="ck_trips_gross_gte_tare",
        ),
        sa.CheckConstraint(
            """
            net_weight_kg IS NULL OR gross_weight_kg IS NULL OR tare_weight_kg IS NULL OR
            net_weight_kg = gross_weight_kg - tare_weight_kg
            """,
            name="ck_trips_net_eq_diff",
        ),
        sa.CheckConstraint(f"status <> 'COMPLETED' OR ({_COMPLETE_TRIP_SQL})", name="ck_trips_completed_complete"),
        sa.CheckConstraint(
            f"source_type NOT IN ('ADMIN_MANUAL', 'EMPTY_RETURN_ADMIN', 'EXCEL_IMPORT') OR ({_COMPLETE_TRIP_SQL})",
            name="ck_trips_strict_sources_complete",
        ),
        sa.CheckConstraint(
            f"review_reason_code <> 'FALLBACK_MINIMAL' OR status = 'PENDING_REVIEW' OR ({_COMPLETE_TRIP_SQL})",
            name="ck_trips_fallback_pending_only",
        ),
        sa.CheckConstraint(
            "source_type NOT IN ('TELEGRAM_TRIP_SLIP', 'EXCEL_IMPORT') OR source_reference_key IS NOT NULL",
            name="ck_trips_imported_source_reference_key",
        ),
        sa.ForeignKeyConstraint(["base_trip_id"], ["trip_trips.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_no", name="uq_trip_trips_trip_no"),
    )
    op.create_index("ix_trips_status_datetime", "trip_trips", ["status", "trip_datetime_utc", "id"], unique=False)
    op.create_index(
        "ix_trips_driver_window",
        "trip_trips",
        ["driver_id", "trip_datetime_utc", "planned_end_utc"],
        unique=False,
    )
    op.create_index(
        "ix_trips_vehicle_window",
        "trip_trips",
        ["vehicle_id", "trip_datetime_utc", "planned_end_utc"],
        unique=False,
    )
    op.create_index(
        "ix_trips_trailer_window",
        "trip_trips",
        ["trailer_id", "trip_datetime_utc", "planned_end_utc"],
        unique=False,
    )
    op.create_index(
        "ix_trips_route_pair_datetime", "trip_trips", ["route_pair_id", "trip_datetime_utc", "id"], unique=False
    )
    op.create_index("ix_trips_base_trip", "trip_trips", ["base_trip_id"], unique=False)
    op.create_index(
        "uq_trips_empty_return_base_trip",
        "trip_trips",
        ["base_trip_id"],
        unique=True,
        postgresql_where=sa.text("is_empty_return = true"),
    )
    op.create_index(
        "uq_trips_source_slip_no_telegram",
        "trip_trips",
        ["source_slip_no"],
        unique=True,
        postgresql_where=sa.text("source_type = 'TELEGRAM_TRIP_SLIP' AND source_slip_no IS NOT NULL"),
    )
    op.create_index(
        "uq_trips_source_reference_key",
        "trip_trips",
        ["source_reference_key"],
        unique=True,
        postgresql_where=sa.text("source_reference_key IS NOT NULL"),
    )

    op.create_table(
        "trip_trip_evidence",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("trip_id", sa.String(length=26), nullable=False),
        sa.Column("evidence_source", sa.String(length=30), nullable=False),
        sa.Column("evidence_kind", sa.String(length=20), nullable=False),
        sa.Column("source_slip_no", sa.String(length=100), nullable=True),
        sa.Column("telegram_message_id", sa.String(length=50), nullable=True),
        sa.Column("file_key", sa.String(length=500), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("raw_text_ref", sa.String(length=200), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("normalized_truck_plate", sa.String(length=50), nullable=True),
        sa.Column("normalized_trailer_plate", sa.String(length=50), nullable=True),
        sa.Column("origin_name_raw", sa.String(length=200), nullable=True),
        sa.Column("destination_name_raw", sa.String(length=200), nullable=True),
        sa.Column("raw_payload_json", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trip_trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_trip_id", "trip_trip_evidence", ["trip_id"], unique=False)
    op.create_index(
        "ix_evidence_source_slip", "trip_trip_evidence", ["evidence_source", "source_slip_no"], unique=False
    )
    op.create_index("ix_evidence_telegram_msg", "trip_trip_evidence", ["telegram_message_id"], unique=False)
    op.create_index("ix_evidence_row_number", "trip_trip_evidence", ["row_number"], unique=False)

    op.create_table(
        "trip_trip_enrichment",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("trip_id", sa.String(length=26), nullable=False),
        sa.Column("enrichment_status", sa.String(length=10), nullable=False),
        sa.Column("route_status", sa.String(length=10), nullable=False),
        sa.Column("data_quality_flag", sa.String(length=10), nullable=False),
        sa.Column("enrichment_attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_enrichment_error_code", sa.String(length=100), nullable=True),
        sa.Column("next_retry_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(length=50), nullable=True),
        sa.Column("claim_expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by_worker", sa.String(length=50), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trip_trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id"),
    )
    op.create_index(
        "ix_enrichment_status_retry", "trip_trip_enrichment", ["enrichment_status", "next_retry_at_utc"], unique=False
    )
    op.create_index("ix_enrichment_route", "trip_trip_enrichment", ["route_status"], unique=False)
    op.create_index("ix_enrichment_claim_exp", "trip_trip_enrichment", ["claim_expires_at_utc"], unique=False)

    op.create_table(
        "trip_trip_timeline",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("trip_id", sa.String(length=26), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=50), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trip_trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_timeline_trip_created", "trip_trip_timeline", ["trip_id", "created_at_utc"], unique=False)
    op.create_index("ix_timeline_event_created", "trip_trip_timeline", ["event_type", "created_at_utc"], unique=False)

    op.create_table(
        "trip_trip_delete_audit",
        sa.Column("audit_id", sa.String(length=26), nullable=False),
        sa.Column("trip_id", sa.String(length=26), nullable=False),
        sa.Column("trip_no", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=50), nullable=False),
        sa.Column("actor_role", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("deleted_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index("ix_trip_delete_audit_trip", "trip_trip_delete_audit", ["trip_id", "deleted_at_utc"], unique=False)
    op.create_index(
        "ix_trip_delete_audit_actor", "trip_trip_delete_audit", ["actor_id", "deleted_at_utc"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_trip_delete_audit_actor", table_name="trip_trip_delete_audit")
    op.drop_index("ix_trip_delete_audit_trip", table_name="trip_trip_delete_audit")
    op.drop_table("trip_trip_delete_audit")

    op.drop_index("ix_timeline_event_created", table_name="trip_trip_timeline")
    op.drop_index("ix_timeline_trip_created", table_name="trip_trip_timeline")
    op.drop_table("trip_trip_timeline")

    op.drop_index("ix_enrichment_claim_exp", table_name="trip_trip_enrichment")
    op.drop_index("ix_enrichment_route", table_name="trip_trip_enrichment")
    op.drop_index("ix_enrichment_status_retry", table_name="trip_trip_enrichment")
    op.drop_table("trip_trip_enrichment")

    op.drop_index("ix_evidence_row_number", table_name="trip_trip_evidence")
    op.drop_index("ix_evidence_telegram_msg", table_name="trip_trip_evidence")
    op.drop_index("ix_evidence_source_slip", table_name="trip_trip_evidence")
    op.drop_index("ix_evidence_trip_id", table_name="trip_trip_evidence")
    op.drop_table("trip_trip_evidence")

    op.drop_index(
        "uq_trips_source_reference_key",
        table_name="trip_trips",
        postgresql_where=sa.text("source_reference_key IS NOT NULL"),
    )
    op.drop_index(
        "uq_trips_source_slip_no_telegram",
        table_name="trip_trips",
        postgresql_where=sa.text("source_type = 'TELEGRAM_TRIP_SLIP' AND source_slip_no IS NOT NULL"),
    )
    op.drop_index(
        "uq_trips_empty_return_base_trip",
        table_name="trip_trips",
        postgresql_where=sa.text("is_empty_return = true"),
    )
    op.drop_index("ix_trips_base_trip", table_name="trip_trips")
    op.drop_index("ix_trips_route_pair_datetime", table_name="trip_trips")
    op.drop_index("ix_trips_trailer_window", table_name="trip_trips")
    op.drop_index("ix_trips_vehicle_window", table_name="trip_trips")
    op.drop_index("ix_trips_driver_window", table_name="trip_trips")
    op.drop_index("ix_trips_status_datetime", table_name="trip_trips")
    op.drop_table("trip_trips")

    op.drop_index("ix_outbox_event_name", table_name="trip_outbox")
    op.drop_index("ix_outbox_aggregate", table_name="trip_outbox")
    op.drop_index("ix_outbox_status_attempt_created", table_name="trip_outbox")
    op.drop_table("trip_outbox")

    op.drop_index("ix_idempotency_expires", table_name="trip_idempotency_records")
    op.drop_table("trip_idempotency_records")
