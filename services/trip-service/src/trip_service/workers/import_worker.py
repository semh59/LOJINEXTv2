"""Import worker — V8 Section 12.

Processes import jobs asynchronously. Supports STRICT and PARTIAL modes.

V8 Section 12.6 — STRICT mode semantics:
- Full validation pass over ALL rows BEFORE persisting any trip data
- If any row fails → job FAILED, zero trips persisted
- All row-level errors MUST still be recorded in trip_import_job_rows
  with row_status = REJECTED

V8 Section 12.6 — PARTIAL mode:
- Valid rows imported, invalid rows rejected individually
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import openpyxl
from sqlalchemy import select
from ulid import ULID

from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.enums import (
    ActorType,
    DataQualityFlag,
    EnrichmentStatus,
    EvidenceKind,
    EvidenceSource,
    ImportJobStatus,
    ImportMode,
    ImportRowStatus,
    RouteStatus,
    SourceType,
    TripStatus,
)
from trip_service.models import (
    TripImportJob,
    TripImportJobRow,
    TripOutbox,
    TripTrip,
    TripTripEnrichment,
    TripTripEvidence,
    TripTripTimeline,
)

logger = logging.getLogger("trip_service.import_worker")


def _generate_id() -> str:
    return str(ULID())


def _now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


def _local_to_utc(local_str: str, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    local_dt = datetime.fromisoformat(local_str).replace(tzinfo=tz)
    return local_dt.astimezone(ZoneInfo("UTC"))


async def process_import_job(job_id: str) -> None:
    """Process a single import job.

    Called after job is created. Reads the .xlsx file, validates rows,
    and creates trips based on import mode.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(TripImportJob).where(TripImportJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("Import job %s not found", job_id)
            return

        if job.status != ImportJobStatus.PENDING:
            logger.warning("Import job %s is not PENDING, skipping", job_id)
            return

        # Mark as RUNNING
        now = _now_utc()
        job.status = ImportJobStatus.RUNNING
        job.updated_at_utc = now
        await session.commit()

    try:
        # Read the Excel file
        file_path = Path(settings.storage_local_path) / job.file_key
        if not file_path.exists():
            raise FileNotFoundError(f"Import file not found: {job.file_key}")

        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active
        if ws is None:
            raise ValueError("Workbook has no active sheet")

        # Read header row
        rows_data = list(ws.iter_rows(min_row=1, values_only=True))
        wb.close()

        if len(rows_data) < 2:
            raise ValueError("File has no data rows")

        headers = [str(h).strip().lower() if h else "" for h in rows_data[0]]
        data_rows = rows_data[1:]

        # Validate all rows first (for both STRICT and PARTIAL)
        validated: list[tuple[int, dict[str, Any], str | None, str | None]] = []

        for idx, row_values in enumerate(data_rows, start=2):
            row_dict = dict(zip(headers, row_values, strict=False))
            error_code, error_detail = _validate_import_row(row_dict, headers)

            if error_code:
                validated.append((idx, row_dict, error_code, error_detail))
            else:
                validated.append((idx, row_dict, None, None))

        # Process based on mode
        async with async_session_factory() as session:
            result = await session.execute(select(TripImportJob).where(TripImportJob.id == job_id))
            job = result.scalar_one_or_none()
            if job is None:
                return

            import_mode = job.import_mode
            has_errors = any(v[2] is not None for v in validated)

            if import_mode == ImportMode.STRICT and has_errors:
                # STRICT: Record ALL errors but create NO trips
                for row_num, row_dict, err_code, err_detail in validated:
                    import_row = TripImportJobRow(
                        id=_generate_id(),
                        job_id=job_id,
                        row_number=row_num,
                        row_status=ImportRowStatus.REJECTED,
                        raw_row_json=json.dumps(row_dict, default=str),
                        error_code=err_code or "STRICT_MODE_ROLLBACK",
                        error_detail=err_detail or "Rejected due to STRICT mode — other rows have errors",
                        created_at_utc=_now_utc(),
                        updated_at_utc=_now_utc(),
                    )
                    session.add(import_row)

                job.status = ImportJobStatus.FAILED
                job.rejected_count = len(validated)
                job.error_summary_json = json.dumps(
                    {
                        "mode": "STRICT",
                        "reason": "Validation failed for one or more rows",
                        "total_rows": len(validated),
                        "failed_rows": sum(1 for v in validated if v[2] is not None),
                    }
                )
                job.completed_at_utc = _now_utc()
                job.updated_at_utc = _now_utc()
                await session.commit()
                logger.info(
                    "Import job %s: STRICT mode FAILED — %d errors found", job_id, sum(1 for v in validated if v[2])
                )
                return

            # PARTIAL mode (or STRICT with no errors): process valid rows
            imported = 0
            rejected = 0

            for row_num, row_dict, err_code, err_detail in validated:
                if err_code:
                    # Record rejected row
                    import_row = TripImportJobRow(
                        id=_generate_id(),
                        job_id=job_id,
                        row_number=row_num,
                        row_status=ImportRowStatus.REJECTED,
                        raw_row_json=json.dumps(row_dict, default=str),
                        error_code=err_code,
                        error_detail=err_detail,
                        created_at_utc=_now_utc(),
                        updated_at_utc=_now_utc(),
                    )
                    session.add(import_row)
                    rejected += 1
                    continue

                # Create trip from valid row
                now = _now_utc()
                trip_id = _generate_id()
                trip_no = row_dict.get("trip_no", f"IMP-{job_id[:8]}-{row_num}")

                try:
                    trip_datetime_utc = _local_to_utc(
                        str(row_dict.get("trip_datetime_local", "")),
                        str(row_dict.get("trip_timezone", "Europe/Istanbul")),
                    )
                except Exception:
                    trip_datetime_utc = now

                tare = int(row_dict.get("tare_weight_kg", 0) or 0)
                gross = int(row_dict.get("gross_weight_kg", 0) or 0)
                net = int(row_dict.get("net_weight_kg", 0) or 0)

                trip = TripTrip(
                    id=trip_id,
                    trip_no=trip_no,
                    source_type=SourceType.EXCEL_IMPORT,
                    driver_id=str(row_dict.get("driver_id", "")),
                    vehicle_id=str(row_dict.get("vehicle_id", "")) if row_dict.get("vehicle_id") else None,
                    trailer_id=str(row_dict.get("trailer_id", "")) if row_dict.get("trailer_id") else None,
                    route_id=str(row_dict.get("route_id", "")) if row_dict.get("route_id") else None,
                    trip_datetime_utc=trip_datetime_utc,
                    trip_timezone=str(row_dict.get("trip_timezone", "Europe/Istanbul")),
                    tare_weight_kg=tare,
                    gross_weight_kg=gross,
                    net_weight_kg=net,
                    is_empty_return=False,
                    status=TripStatus.PENDING_REVIEW,
                    version=1,
                    created_by_actor_type=ActorType.SYSTEM,
                    created_by_actor_id=f"import-job-{job_id}",
                    created_at_utc=now,
                    updated_at_utc=now,
                )
                session.add(trip)

                # Evidence
                evidence = TripTripEvidence(
                    id=_generate_id(),
                    trip_id=trip_id,
                    evidence_source=EvidenceSource.EXCEL_IMPORT,
                    evidence_kind=EvidenceKind.IMPORT_ROW,
                    row_number=row_num,
                    origin_name_raw=str(row_dict.get("origin_name", "")) if row_dict.get("origin_name") else None,
                    destination_name_raw=str(row_dict.get("destination_name", ""))
                    if row_dict.get("destination_name")
                    else None,
                    raw_payload_json=json.dumps(row_dict, default=str),
                    created_at_utc=now,
                )
                session.add(evidence)

                # Enrichment
                enrichment = TripTripEnrichment(
                    id=_generate_id(),
                    trip_id=trip_id,
                    enrichment_status=EnrichmentStatus.PENDING,
                    route_status=RouteStatus.READY if row_dict.get("route_id") else RouteStatus.PENDING,
                    data_quality_flag=DataQualityFlag.HIGH,
                    enrichment_attempt_count=0,
                    created_at_utc=now,
                    updated_at_utc=now,
                )
                session.add(enrichment)

                # Timeline
                timeline = TripTripTimeline(
                    id=_generate_id(),
                    trip_id=trip_id,
                    event_type="TRIP_CREATED",
                    actor_type=ActorType.SYSTEM,
                    actor_id=f"import-job-{job_id}",
                    note=f"Imported from row {row_num}",
                    created_at_utc=now,
                )
                session.add(timeline)

                # Outbox
                outbox = TripOutbox(
                    event_id=_generate_id(),
                    aggregate_type="TRIP",
                    aggregate_id=trip_id,
                    aggregate_version=1,
                    event_name="trip.created.v1",
                    schema_version=1,
                    payload_json=json.dumps({"trip_id": trip_id, "source_type": "EXCEL_IMPORT"}, default=str),
                    partition_key=trip_id,
                    publish_status="PENDING",
                    attempt_count=0,
                    created_at_utc=now,
                )
                session.add(outbox)

                # Import row record
                import_row = TripImportJobRow(
                    id=_generate_id(),
                    job_id=job_id,
                    row_number=row_num,
                    row_status=ImportRowStatus.IMPORTED,
                    created_trip_id=trip_id,
                    driver_code_raw=str(row_dict.get("driver_code", "")) if row_dict.get("driver_code") else None,
                    raw_row_json=json.dumps(row_dict, default=str),
                    created_at_utc=now,
                    updated_at_utc=now,
                )
                session.add(import_row)
                imported += 1

            # Update job status
            job.imported_count = imported
            job.rejected_count = rejected
            job.enrichment_pending_count = imported  # All new trips need enrichment
            job.status = ImportJobStatus.COMPLETED
            job.completed_at_utc = _now_utc()
            job.updated_at_utc = _now_utc()

            await session.commit()
            logger.info(
                "Import job %s: COMPLETED — %d imported, %d rejected",
                job_id,
                imported,
                rejected,
            )

    except Exception as e:
        logger.error("Import job %s: FAILED — %s", job_id, e)
        async with async_session_factory() as session:
            result = await session.execute(select(TripImportJob).where(TripImportJob.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                job.status = ImportJobStatus.FAILED
                job.error_summary_json = json.dumps({"error": str(e)[:500]})
                job.completed_at_utc = _now_utc()
                job.updated_at_utc = _now_utc()
                await session.commit()


def _validate_import_row(
    row: dict[str, Any],
    headers: list[str],
) -> tuple[str | None, str | None]:
    """Validate a single import row.

    Returns (error_code, error_detail) or (None, None) if valid.
    """
    # Required fields
    if not row.get("driver_id") and not row.get("driver_code"):
        return "MISSING_DRIVER", "driver_id or driver_code is required"

    if not row.get("trip_datetime_local"):
        return "MISSING_DATETIME", "trip_datetime_local is required"

    # Weight validation
    try:
        tare = int(row.get("tare_weight_kg", 0) or 0)
        gross = int(row.get("gross_weight_kg", 0) or 0)
        net = int(row.get("net_weight_kg", 0) or 0)
    except (ValueError, TypeError):
        return "INVALID_WEIGHT", "Weight fields must be integers"

    if tare < 0 or gross < 0 or net < 0:
        return "NEGATIVE_WEIGHT", "Weight fields must be non-negative"

    if gross < tare:
        return "WEIGHT_MISMATCH", "gross_weight_kg must be >= tare_weight_kg"

    return None, None
