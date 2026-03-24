"""remove_weather_enrichment

Revision ID: 15fb296d4296
Revises: 08b0b143dd9b
Create Date: 2026-03-24 21:07:32.586942
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "15fb296d4296"
down_revision: Union[str, None] = "08b0b143dd9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_enrichment_weather", table_name="trip_trip_enrichment")
    op.drop_column("trip_trip_enrichment", "weather_status")
    op.drop_column("trip_import_job", "skip_weather_enrichment")


def downgrade() -> None:
    op.add_column(
        "trip_import_job", sa.Column("skip_weather_enrichment", sa.BOOLEAN(), server_default="false", nullable=False)
    )
    op.add_column("trip_trip_enrichment", sa.Column("weather_status", sa.VARCHAR(length=50), nullable=True))
    op.create_index("ix_enrichment_weather", "trip_trip_enrichment", ["weather_status"], unique=False)
