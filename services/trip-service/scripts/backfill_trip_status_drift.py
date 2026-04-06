"""Backfill legacy trip statuses after the Phase A compatibility deploy."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = SERVICE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trip_service.database import async_session_factory
from trip_service.models import TripTrip

BLOCKING_STATUSES = ("REQUESTED", "IN_PROGRESS")
LEGACY_DELETED_STATUS = "CANCELLED"
LEGACY_ASSIGNED_STATUS = "ASSIGNED"
ASSIGNED_TO_COMPLETED_SOURCES = ("ADMIN_MANUAL", "EMPTY_RETURN_ADMIN")


@dataclass(frozen=True)
class DriftRow:
    """Minimal status drift row detail for operator review."""

    id: str
    status: str
    source_type: str


@dataclass(frozen=True)
class BackfillSummary:
    """Serializable summary for dry-run and apply executions."""

    apply: bool
    blocking_rows: list[DriftRow]
    planned_counts: dict[str, int]
    applied_counts: dict[str, int]
    remaining_counts: dict[str, int]


async def _select_rows(session: AsyncSession, statuses: tuple[str, ...]) -> list[DriftRow]:
    result = await session.execute(
        select(TripTrip.id, TripTrip.status, TripTrip.source_type)
        .where(TripTrip.status.in_(statuses))
        .order_by(TripTrip.status.asc(), TripTrip.id.asc())
    )
    return [DriftRow(id=row.id, status=row.status, source_type=row.source_type) for row in result]


def _count_rows(rows: list[DriftRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


async def run_backfill(*, apply: bool, session_factory=async_session_factory) -> BackfillSummary:
    """Dry-run or apply the supported status drift conversions."""
    async with session_factory() as session:
        blocking_rows = await _select_rows(session, BLOCKING_STATUSES)
        cancelled_rows = await _select_rows(session, (LEGACY_DELETED_STATUS,))
        assigned_rows = await _select_rows(session, (LEGACY_ASSIGNED_STATUS,))

        convertible_assigned = [row for row in assigned_rows if row.source_type in ASSIGNED_TO_COMPLETED_SOURCES]
        planned_counts = {
            LEGACY_DELETED_STATUS: len(cancelled_rows),
            LEGACY_ASSIGNED_STATUS: len(convertible_assigned),
        }
        applied_counts = {
            LEGACY_DELETED_STATUS: 0,
            LEGACY_ASSIGNED_STATUS: 0,
        }

        if apply and not blocking_rows:
            if cancelled_rows:
                result = await session.execute(
                    update(TripTrip)
                    .where(TripTrip.status == LEGACY_DELETED_STATUS)
                    .values(status="SOFT_DELETED")
                )
                applied_counts[LEGACY_DELETED_STATUS] = int(result.rowcount or 0)
            if convertible_assigned:
                result = await session.execute(
                    update(TripTrip)
                    .where(
                        TripTrip.status == LEGACY_ASSIGNED_STATUS,
                        TripTrip.source_type.in_(ASSIGNED_TO_COMPLETED_SOURCES),
                    )
                    .values(status="COMPLETED")
                )
                applied_counts[LEGACY_ASSIGNED_STATUS] = int(result.rowcount or 0)
            await session.commit()
        else:
            await session.rollback()

    async with session_factory() as session:
        remaining_rows = await _select_rows(
            session,
            (
                LEGACY_DELETED_STATUS,
                LEGACY_ASSIGNED_STATUS,
                *BLOCKING_STATUSES,
            ),
        )

    return BackfillSummary(
        apply=apply,
        blocking_rows=blocking_rows,
        planned_counts=planned_counts,
        applied_counts=applied_counts,
        remaining_counts=_count_rows(remaining_rows),
    )


def exit_code_for_summary(summary: BackfillSummary) -> int:
    """Return the shell exit code for the executed run."""
    if summary.blocking_rows:
        return 1
    if summary.apply and summary.remaining_counts:
        return 1
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill legacy trip status drift after the Phase A deploy.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect drift without applying changes. This is the default mode.",
    )
    parser.add_argument("--apply", action="store_true", help="Apply the supported conversions instead of dry-run mode.")
    return parser.parse_args()


def _summary_payload(summary: BackfillSummary) -> dict[str, object]:
    return {
        "apply": summary.apply,
        "blocking_rows": [asdict(row) for row in summary.blocking_rows],
        "planned_counts": summary.planned_counts,
        "applied_counts": summary.applied_counts,
        "remaining_counts": summary.remaining_counts,
    }


async def _async_main() -> int:
    args = _parse_args()
    summary = await run_backfill(apply=args.apply)
    print(json.dumps(_summary_payload(summary), indent=2, sort_keys=True))
    return exit_code_for_summary(summary)


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
