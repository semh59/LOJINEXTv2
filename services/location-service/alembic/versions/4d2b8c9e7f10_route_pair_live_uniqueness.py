"""route pair live uniqueness

Revision ID: 4d2b8c9e7f10
Revises: 0d5f12e97db6
Create Date: 2026-03-30 12:30:00
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4d2b8c9e7f10"
down_revision: str | None = "0d5f12e97db6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicates = (
        connection.execute(
            sa.text(
                """
            SELECT
                origin_location_id::text AS origin_location_id,
                destination_location_id::text AS destination_location_id,
                profile_code,
                COUNT(*) AS duplicate_count
            FROM route_pairs
            WHERE pair_status IN ('ACTIVE', 'DRAFT')
            GROUP BY origin_location_id, destination_location_id, profile_code
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC, origin_location_id, destination_location_id, profile_code
            """
            )
        )
        .mappings()
        .all()
    )
    if duplicates:
        detail = "; ".join(
            f"({row['origin_location_id']}, {row['destination_location_id']}, "
            f"{row['profile_code']}) x{row['duplicate_count']}"
            for row in duplicates
        )
        raise RuntimeError(
            f"Cannot create idx_route_pairs_live_unique because duplicate ACTIVE/DRAFT route_pairs exist: {detail}"
        )

    op.drop_index("idx_route_pairs_active_unique", table_name="route_pairs")
    op.create_index(
        "idx_route_pairs_live_unique",
        "route_pairs",
        ["origin_location_id", "destination_location_id", "profile_code"],
        unique=True,
        postgresql_where=sa.text("pair_status IN ('ACTIVE', 'DRAFT')"),
    )


def downgrade() -> None:
    op.drop_index("idx_route_pairs_live_unique", table_name="route_pairs")
    op.create_index(
        "idx_route_pairs_active_unique",
        "route_pairs",
        ["origin_location_id", "destination_location_id", "profile_code"],
        unique=True,
        postgresql_where=sa.text("pair_status = 'ACTIVE'"),
    )
