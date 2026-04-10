"""add location_ prefix to all service tables

Revision ID: c1d2e3f4a5b6
Revises: f1a2b3c4d5e6
Create Date: 2026-04-10
"""

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

_TABLES = [
    ("route_pairs", "location_route_pairs"),
    ("routes", "location_routes"),
    ("route_version_counters", "location_route_version_counters"),
    ("route_versions", "location_route_versions"),
    ("route_segments", "location_route_segments"),
    ("processing_runs", "location_processing_runs"),
    ("route_usage_refs", "location_route_usage_refs"),
    ("bulk_refresh_jobs", "location_bulk_refresh_jobs"),
    ("bulk_refresh_job_items", "location_bulk_refresh_job_items"),
    ("idempotency_keys", "location_idempotency_keys"),
    ("worker_heartbeats", "location_worker_heartbeats"),
]


def upgrade() -> None:
    for old_name, new_name in _TABLES:
        op.rename_table(old_name, new_name)


def downgrade() -> None:
    for old_name, new_name in reversed(_TABLES):
        op.rename_table(new_name, old_name)
