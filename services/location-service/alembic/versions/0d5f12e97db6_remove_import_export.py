"""remove_import_export

Revision ID: 0d5f12e97db6
Revises: 9f4e4fe14d8c
Create Date: 2026-03-28 19:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0d5f12e97db6"
down_revision: Union[str, None] = "9f4e4fe14d8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("route_import_job_row_errors")
    op.drop_table("route_import_job_rows")
    op.drop_column("processing_runs", "import_job_id")
    op.drop_table("route_import_jobs")
    op.drop_table("route_export_jobs")


def downgrade() -> None:
    op.create_table(
        "route_export_jobs",
        sa.Column("export_job_id", sa.UUID(), nullable=False),
        sa.Column("job_status", sa.String(length=50), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("include_segments", sa.Boolean(), nullable=False),
        sa.Column("file_storage_ref", sa.String(length=512), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("export_job_id"),
    )
    op.create_table(
        "route_import_jobs",
        sa.Column("import_job_id", sa.UUID(), nullable=False),
        sa.Column("file_storage_ref", sa.String(length=512), nullable=False),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("job_status", sa.String(length=50), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("processed_rows", sa.Integer(), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("import_job_id"),
        sa.UniqueConstraint("content_checksum", "mode", name="uq_route_import_jobs_checksum_mode"),
    )
    op.add_column("processing_runs", sa.Column("import_job_id", sa.UUID(), nullable=True))
    op.create_foreign_key(None, "processing_runs", "route_import_jobs", ["import_job_id"], ["import_job_id"])
    op.create_table(
        "route_import_job_rows",
        sa.Column("import_job_id", sa.UUID(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("row_status", sa.String(length=50), nullable=False),
        sa.Column("raw_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("route_pair_id", sa.String(length=26), nullable=True),
        sa.Column("processing_run_id", sa.String(length=26), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["import_job_id"], ["route_import_jobs.import_job_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_run_id"], ["processing_runs.processing_run_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["route_pair_id"], ["route_pairs.route_pair_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("import_job_id", "row_no"),
    )
    op.create_table(
        "route_import_job_row_errors",
        sa.Column("import_job_id", sa.UUID(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("error_seq", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=False),
        sa.Column("error_message", sa.String(length=512), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_job_id", "row_no"],
            ["route_import_job_rows.import_job_id", "route_import_job_rows.row_no"],
            name="fk_route_import_job_row_errors_row",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("import_job_id", "row_no", "error_seq"),
    )
