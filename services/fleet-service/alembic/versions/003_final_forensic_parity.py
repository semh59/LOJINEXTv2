"""final forensic parity

Revision ID: 003_final_forensic_parity
Revises: 002_add_fleet_audit_log
Create Date: 2026-04-07
"""

from alembic import op

revision = "003_final_forensic_parity"
down_revision = "002_add_fleet_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Audit Log Index Renaming (idx_ -> ix_)
    op.drop_index("idx_fleet_audit_agg_created", table_name="fleet_audit_log")
    op.create_index(
        "ix_fleet_audit_log_agg_created",
        "fleet_audit_log",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
    )


def downgrade() -> None:
    pass
