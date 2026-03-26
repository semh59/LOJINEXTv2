"""Export Logic for Route Pairs.

Handles memory-efficient streaming of Route Pair data to CSV.
"""

import csv
import io
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.orm import aliased

from location_service.database import async_session_factory
from location_service.models import LocationPoint, RoutePair


async def generate_export_csv_stream() -> AsyncGenerator[str, None]:
    """Stream Route Pair data as CSV rows."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "pair_id",
            "pair_code",
            "status",
            "origin_code",
            "destination_code",
            "active_fwd_version",
            "active_rev_version",
        ]
    )
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    async with async_session_factory() as session:
        orig_alias = aliased(LocationPoint)
        dest_alias = aliased(LocationPoint)

        # Joined query for origin and destination codes
        stmt = (
            select(
                RoutePair.route_pair_id,
                RoutePair.pair_code,
                RoutePair.pair_status,
                RoutePair.current_active_forward_version_no,
                RoutePair.current_active_reverse_version_no,
                orig_alias.code.label("origin_code"),
                dest_alias.code.label("destination_code"),
            )
            .join(orig_alias, RoutePair.origin_location_id == orig_alias.location_id)
            .join(dest_alias, RoutePair.destination_location_id == dest_alias.location_id)
            .order_by(RoutePair.pair_code)
        )

        result = await session.stream(stmt)
        async for row in result:
            writer.writerow(
                [
                    str(row.route_pair_id),
                    row.pair_code,
                    row.pair_status.value if hasattr(row.pair_status, "value") else str(row.pair_status),
                    row.origin_code,
                    row.destination_code,
                    row.current_active_forward_version_no if row.current_active_forward_version_no is not None else "",
                    row.current_active_reverse_version_no if row.current_active_reverse_version_no is not None else "",
                ]
            )
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
