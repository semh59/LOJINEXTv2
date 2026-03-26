"""Import Logic for Route Pairs (Section 4.3).

Handles high-performance batch creation of Route Pairs from CSV data.
"""

import csv
import io
import logging
from dataclasses import dataclass
from typing import List, Tuple

from sqlalchemy import func, insert, select, tuple_

from location_service.database import async_session_factory
from location_service.domain.codes import generate_pair_code
from location_service.enums import PairStatus
from location_service.models import LocationPoint, RoutePair

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result of an import operation."""

    total_rows: int
    success_count: int
    failure_count: int
    errors: List[Tuple[int, str]]  # (row_index, error_message)


async def process_import_csv(file_content: bytes) -> ImportResult:
    """Parse CSV and create Route Pairs in batch.

    CSV format expected: origin_code, destination_code
    """
    stream = io.StringIO(file_content.decode("utf-8"))
    reader = csv.reader(stream)

    # Skip header if it exists
    try:
        header = next(reader)
        if not header or "code" not in header[0].lower():
            stream.seek(0)
    except StopIteration:
        return ImportResult(0, 0, 0, [])

    rows = list(reader)
    total_items = len(rows)

    if not total_items:
        return ImportResult(0, 0, 0, [])

    # Extract all unique codes for batch validation
    unique_codes = set()
    for row in rows:
        if len(row) >= 2:
            unique_codes.add(row[0].strip().upper())
            unique_codes.add(row[1].strip().upper())

    async with async_session_factory() as session:
        # Batch fetch location IDs
        stmt = select(LocationPoint.code, LocationPoint.location_id).where(
            func.upper(LocationPoint.code).in_(list(unique_codes))
        )
        location_map = {row.code.upper(): row.location_id for row in (await session.execute(stmt)).all()}

        # FINDING-12: Pre-check for existing ACTIVE/DRAFT pairs to produce per-row errors
        # Build (origin_id, dest_id) pairs to check against DB
        valid_pairs_for_check = []
        for row in rows:
            if len(row) >= 2:
                orig_id = location_map.get(row[0].strip().upper())
                dest_id = location_map.get(row[1].strip().upper())
                if orig_id and dest_id:
                    valid_pairs_for_check.append((orig_id, dest_id))

        existing_pairs: set = set()
        if valid_pairs_for_check:
            existing_stmt = select(RoutePair.origin_location_id, RoutePair.destination_location_id).where(
                tuple_(RoutePair.origin_location_id, RoutePair.destination_location_id).in_(valid_pairs_for_check),
                RoutePair.pair_status.in_([PairStatus.ACTIVE, PairStatus.DRAFT]),
            )
            results = (await session.execute(existing_stmt)).all()
            existing_pairs = {(r.origin_location_id, r.destination_location_id) for r in results}

        # Prepare bulk insert values
        to_insert = []
        errors: List[Tuple[int, str]] = []
        success_count = 0

        for i, row in enumerate(rows, start=1):
            if len(row) < 2:
                errors.append((i, "Invalid row format (expected at least 2 columns)"))
                continue

            orig_code = row[0].strip().upper()
            dest_code = row[1].strip().upper()

            orig_id = location_map.get(orig_code)
            dest_id = location_map.get(dest_code)

            if not orig_id or not dest_id:
                missing = []
                if not orig_id:
                    missing.append(orig_code)
                if not dest_id:
                    missing.append(dest_code)
                errors.append((i, f"Missing points: {', '.join(missing)}"))
                continue

            # FINDING-12: Per-row duplicate error instead of DB constraint failure
            if (orig_id, dest_id) in existing_pairs:
                errors.append((i, f"Pair {orig_code}→{dest_code} already exists (ACTIVE or DRAFT)"))
                continue

            to_insert.append(
                {
                    "pair_code": generate_pair_code(),
                    "pair_status": PairStatus.DRAFT,
                    "origin_location_id": orig_id,
                    "destination_location_id": dest_id,
                }
            )
            success_count += 1

        if to_insert:
            # High-performance SQLAlchemy Core bulk insert
            await session.execute(insert(RoutePair), to_insert)
            await session.commit()

    return ImportResult(total_rows=total_items, success_count=success_count, failure_count=len(errors), errors=errors)
