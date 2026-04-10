"""fleet_timestamp_timezone

Convert all bare TIMESTAMP columns to TIMESTAMPTZ across fleet-service.

20 columns across 9 tables were defined without DateTime(timezone=True),
causing PostgreSQL to store them as TIMESTAMP (without timezone) instead
of TIMESTAMPTZ. This migration corrects the column types in-place.

Revision ID: 006_fleet_timestamp_timezone
Revises: 005_outbox_platform_standard_fields
Create Date: 2026-04-10
"""

import sqlalchemy as sa

from alembic import op

revision = "006_fleet_timestamp_timezone"
down_revision = "005_outbox_std_fields"
branch_labels = None
depends_on = None

TZ = sa.TIMESTAMP(timezone=True)
NO_TZ = sa.TIMESTAMP()


def upgrade() -> None:
    _alter(
        "fleet_vehicles",
        [
            ("created_at_utc", False),
            ("updated_at_utc", False),
            ("soft_deleted_at_utc", True),
        ],
    )
    _alter(
        "fleet_trailers",
        [
            ("created_at_utc", False),
            ("updated_at_utc", False),
            ("soft_deleted_at_utc", True),
        ],
    )
    _alter(
        "fleet_vehicle_spec_versions",
        [
            ("effective_from_utc", False),
            ("effective_to_utc", True),
            ("created_at_utc", False),
        ],
    )
    _alter(
        "fleet_trailer_spec_versions",
        [
            ("effective_from_utc", False),
            ("effective_to_utc", True),
            ("created_at_utc", False),
        ],
    )
    _alter(
        "fleet_asset_timeline_events",
        [
            ("occurred_at_utc", False),
        ],
    )
    _alter(
        "fleet_asset_delete_audit",
        [
            ("created_at_utc", False),
        ],
    )
    _alter(
        "fleet_outbox",
        [
            ("next_attempt_at_utc", False),
            ("created_at_utc", False),
            ("published_at_utc", True),
        ],
    )
    _alter(
        "fleet_idempotency_records",
        [
            ("created_at_utc", False),
            ("expires_at_utc", False),
        ],
    )
    _alter(
        "fleet_worker_heartbeats",
        [
            ("recorded_at_utc", False),
        ],
    )


def downgrade() -> None:
    _alter(
        "fleet_worker_heartbeats",
        [
            ("recorded_at_utc", False),
        ],
        reverse=True,
    )
    _alter(
        "fleet_idempotency_records",
        [
            ("created_at_utc", False),
            ("expires_at_utc", False),
        ],
        reverse=True,
    )
    _alter(
        "fleet_outbox",
        [
            ("next_attempt_at_utc", False),
            ("created_at_utc", False),
            ("published_at_utc", True),
        ],
        reverse=True,
    )
    _alter(
        "fleet_asset_delete_audit",
        [
            ("created_at_utc", False),
        ],
        reverse=True,
    )
    _alter(
        "fleet_asset_timeline_events",
        [
            ("occurred_at_utc", False),
        ],
        reverse=True,
    )
    _alter(
        "fleet_trailer_spec_versions",
        [
            ("effective_from_utc", False),
            ("effective_to_utc", True),
            ("created_at_utc", False),
        ],
        reverse=True,
    )
    _alter(
        "fleet_vehicle_spec_versions",
        [
            ("effective_from_utc", False),
            ("effective_to_utc", True),
            ("created_at_utc", False),
        ],
        reverse=True,
    )
    _alter(
        "fleet_trailers",
        [
            ("created_at_utc", False),
            ("updated_at_utc", False),
            ("soft_deleted_at_utc", True),
        ],
        reverse=True,
    )
    _alter(
        "fleet_vehicles",
        [
            ("created_at_utc", False),
            ("updated_at_utc", False),
            ("soft_deleted_at_utc", True),
        ],
        reverse=True,
    )


def _alter(
    table: str,
    columns: list[tuple[str, bool]],
    *,
    reverse: bool = False,
) -> None:
    new_type = NO_TZ if reverse else TZ
    old_type = TZ if reverse else NO_TZ

    # Drop is_selectable if it exists (for fleet_vehicles and fleet_trailers)
    has_selectable = table in ("fleet_vehicles", "fleet_trailers")
    if has_selectable and not reverse:
        op.drop_column(table, "is_selectable")

    for col_name, _nullable in columns:
        op.alter_column(
            table,
            col_name,
            type_=new_type,
            existing_type=old_type,
            postgresql_using=f"{col_name}::timestamptz" if not reverse else f"{col_name}::timestamp",
        )

    # Re-add is_selectable
    if has_selectable and not reverse:
        op.add_column(
            table,
            sa.Column(
                "is_selectable",
                sa.Boolean(),
                sa.Computed("status = 'ACTIVE' AND soft_deleted_at_utc IS NULL", persisted=True),
            ),
        )
