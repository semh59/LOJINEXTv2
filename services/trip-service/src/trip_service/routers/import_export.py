"""Import/Export endpoints and Driver Statement.

V8 Sections 10.11–10.17: File upload, import jobs, export jobs,
export download, and driver statement.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from trip_service.config import settings
from trip_service.database import get_session
from trip_service.enums import (
    ExportJobStatus,
    ImportJobStatus,
    TripStatus,
)
from trip_service.errors import (
    export_file_expired,
    export_file_not_found,
    export_job_not_found,
    export_not_ready,
    idempotency_payload_mismatch,
    import_job_not_found,
    import_unsupported_file_type,
    storage_unavailable,
)
from trip_service.middleware import date_range_to_utc, make_pagination_meta, parse_pagination
from trip_service.models import (
    TripExportJob,
    TripIdempotencyRecord,
    TripImportJob,
    TripTrip,
)
from trip_service.schemas import (
    CreateExportJobRequest,
    CreateImportJobRequest,
    ExportJobResource,
    FileUploadResponse,
    ImportJobResource,
)

router = APIRouter(tags=["import-export"])


def _generate_id() -> str:
    return str(ULID())


def _now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


def _storage_path() -> Path:
    """Resolve local storage directory."""
    p = Path(settings.storage_local_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# V8 Section 10.12 — File Upload
# ---------------------------------------------------------------------------


@router.post("/api/v1/trips/import-files", status_code=201)
async def upload_import_file(
    file: UploadFile,
    request: Request,
) -> FileUploadResponse:
    """V8 Section 10.12 — Upload .xlsx file for import."""
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise import_unsupported_file_type()

    file_key = f"imports/{_generate_id()}/{file.filename}"
    full_path = _storage_path() / file_key

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        full_path.write_bytes(content)
    except Exception:
        raise storage_unavailable()

    return FileUploadResponse(file_key=file_key)


# ---------------------------------------------------------------------------
# V8 Section 10.13 — Create Import Job
# ---------------------------------------------------------------------------


async def _check_idempotency(
    session: AsyncSession,
    key: str | None,
    endpoint_fp: str,
    request_hash: str,
) -> JSONResponse | None:
    """Shared idempotency check — same logic as trips.py."""
    if not key:
        return None

    stmt = select(TripIdempotencyRecord).where(
        TripIdempotencyRecord.idempotency_key == key,
        TripIdempotencyRecord.endpoint_fingerprint == endpoint_fp,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is None:
        return None
    if existing.request_hash != request_hash:
        raise idempotency_payload_mismatch()
    return JSONResponse(
        status_code=existing.response_status,
        content=json.loads(existing.response_body_json),
    )


async def _save_idempotency(
    session: AsyncSession,
    key: str,
    endpoint_fp: str,
    request_hash: str,
    status: int,
    body: dict[str, Any],
) -> None:
    """Persist idempotency record."""
    now = _now_utc()
    record = TripIdempotencyRecord(
        idempotency_key=key,
        endpoint_fingerprint=endpoint_fp,
        request_hash=request_hash,
        response_status=status,
        response_body_json=json.dumps(body, default=str),
        created_at_utc=now,
        expires_at_utc=now + timedelta(hours=settings.idempotency_retention_hours),
    )
    session.add(record)


def _canonicalize(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@router.post("/api/v1/trips/import-jobs", status_code=201)
async def create_import_job(
    body: CreateImportJobRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
) -> ImportJobResource:
    """V8 Section 10.13 — Create async import job."""
    request_body = body.model_dump()
    request_hash = _canonicalize(request_body)
    endpoint_fp = f"import_job:{x_actor_id}"

    replay = await _check_idempotency(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay  # type: ignore

    # BUG-08: Prevent path traversal via user-supplied file_key
    storage_root = _storage_path().resolve()
    full_path = (storage_root / body.file_key).resolve()
    # Ensure full_path is inside storage_root
    if storage_root not in full_path.parents and full_path != storage_root:
        raise import_unsupported_file_type()
    if not full_path.exists():
        raise storage_unavailable()

    now = _now_utc()
    job = TripImportJob(
        id=_generate_id(),
        file_key=body.file_key,
        status=ImportJobStatus.PENDING,
        import_mode=body.import_mode,
        created_by_admin_id=x_actor_id,
        imported_count=0,
        rejected_count=0,
        enrichment_pending_count=0,
        enrichment_failed_count=0,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(job)
    await session.commit()

    resource = ImportJobResource.model_validate(job)
    resource_dict = resource.model_dump(mode="json")

    if idempotency_key:
        await _save_idempotency(session, idempotency_key, endpoint_fp, request_hash, 201, resource_dict)
        await session.commit()

    return JSONResponse(status_code=201, content=resource_dict)  # type: ignore


# ---------------------------------------------------------------------------
# V8 Section 10.14 — Get Import Job Status
# ---------------------------------------------------------------------------


@router.get("/api/v1/trips/import-jobs/{job_id}")
async def get_import_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> ImportJobResource:
    """V8 Section 10.14."""
    result = await session.execute(select(TripImportJob).where(TripImportJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise import_job_not_found(job_id)
    return ImportJobResource.model_validate(job)


# ---------------------------------------------------------------------------
# V8 Section 10.15 — Create Export Job
# ---------------------------------------------------------------------------


@router.post("/api/v1/trips/export-jobs", status_code=201)
async def create_export_job(
    body: CreateExportJobRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
) -> ExportJobResource:
    """V8 Section 10.15 — Create async export job."""
    request_body = body.model_dump(mode="json")
    request_hash = _canonicalize(request_body)
    endpoint_fp = f"export_job:{x_actor_id}"

    replay = await _check_idempotency(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay  # type: ignore

    now = _now_utc()
    job = TripExportJob(
        id=_generate_id(),
        status=ExportJobStatus.PENDING,
        requested_filters_json=json.dumps(request_body, default=str),
        created_by_admin_id=x_actor_id,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(job)
    await session.commit()

    resource = ExportJobResource.model_validate(job)
    resource_dict = resource.model_dump(mode="json")

    if idempotency_key:
        await _save_idempotency(session, idempotency_key, endpoint_fp, request_hash, 201, resource_dict)
        await session.commit()

    return JSONResponse(status_code=201, content=resource_dict)  # type: ignore


# ---------------------------------------------------------------------------
# V8 Section 10.16 — Get Export Job Status
# ---------------------------------------------------------------------------


@router.get("/api/v1/trips/export-jobs/{job_id}")
async def get_export_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> ExportJobResource:
    """V8 Section 10.16."""
    result = await session.execute(select(TripExportJob).where(TripExportJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise export_job_not_found(job_id)
    return ExportJobResource.model_validate(job)


# ---------------------------------------------------------------------------
# V8 Section 10.17 — Export Download
# ---------------------------------------------------------------------------


@router.get("/api/v1/trips/export-jobs/{job_id}/download")
async def download_export(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """V8 Section 10.17 — 302 redirect to file, 409 if not ready, 410 if expired."""
    result = await session.execute(select(TripExportJob).where(TripExportJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise export_job_not_found(job_id)

    if job.status != ExportJobStatus.COMPLETED:
        raise export_not_ready()

    if job.result_file_expires_at_utc and job.result_file_expires_at_utc < _now_utc():
        raise export_file_expired()

    if not job.result_file_key:
        raise export_file_not_found()

    # For local storage: serve the file directly
    full_path = _storage_path() / job.result_file_key
    if not full_path.exists():
        raise export_file_not_found()

    # In prod: 302 to presigned URL. For local dev: 302 to static file route
    return RedirectResponse(url=f"/storage/{job.result_file_key}", status_code=302)


# ---------------------------------------------------------------------------
# V8 Section 10.11 — Driver Statement
# ---------------------------------------------------------------------------


@router.get("/internal/v1/driver/trips")
async def driver_statement(
    request: Request,
    session: AsyncSession = Depends(get_session),
    driver_id: str = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    timezone: str = Query("Europe/Istanbul"),
    include_empty_returns: bool = Query(False),  # V8: default false
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    """V8 Section 10.11 — Driver statement with fallback chain.

    V8 Section 11.2: Field fallback order:
    - truck_plate → evidence.normalized_truck_plate → "" (evidence table)
    - from/to → Location Service display name (by route_id) → evidence origin/destination_name_raw → ""
    - net_weight_kg (V8 renamed from tonnage) → integer kg

    V8 Section 9.6: Timeline items sorted created_at_utc ASC (chronological)
    """
    from sqlalchemy.orm import selectinload

    pagination = parse_pagination(page, per_page)

    # Build query
    stmt = (
        select(TripTrip)
        .options(selectinload(TripTrip.evidence))
        .where(
            TripTrip.driver_id == driver_id,
            TripTrip.status == TripStatus.COMPLETED,
        )
    )

    # V8 Section 10.11: include_empty_returns default false
    if not include_empty_returns:
        stmt = stmt.where(TripTrip.is_empty_return.is_(False))

    # Date filter
    if date_from or date_to:
        utc_from, utc_to = date_range_to_utc(date_from, date_to, timezone)
        if utc_from:
            stmt = stmt.where(TripTrip.trip_datetime_utc >= utc_from)
        if utc_to:
            stmt = stmt.where(TripTrip.trip_datetime_utc < utc_to)

    # Count
    count_q = select(func.count()).select_from(stmt.subquery())
    total_items = (await session.execute(count_q)).scalar() or 0

    # Sort by trip_datetime_utc ASC for statement chronological order
    items_q = (
        stmt.order_by(TripTrip.trip_datetime_utc.asc(), TripTrip.id.asc())
        .offset(pagination.offset)
        .limit(pagination.per_page)
    )
    results = await session.execute(items_q)
    trips = results.scalars().all()

    # Map to driver statement rows with V8 Section 11.2 fallback chain
    rows: list[dict[str, Any]] = []
    for trip in trips:
        # Evidence-based fallbacks
        evidence = trip.evidence[-1] if trip.evidence else None
        truck_plate = (evidence.normalized_truck_plate if evidence else None) or ""
        origin_raw = (evidence.origin_name_raw if evidence else None) or ""
        destination_raw = (evidence.destination_name_raw if evidence else None) or ""

        # TODO: Phase 4 enhancement — call Location Service for display names by route_id
        # For now: use evidence raw names as fallback
        from_display = origin_raw
        to_display = destination_raw

        # Convert UTC datetime to local for display
        tz = ZoneInfo(trip.trip_timezone or timezone)
        local_dt = trip.trip_datetime_utc.astimezone(tz)

        rows.append(
            {
                "date": local_dt.strftime("%Y-%m-%d"),
                "truck_plate": truck_plate,
                "from": from_display,
                "to": to_display,
                "net_weight_kg": trip.net_weight_kg,  # V8: renamed from tonnage
                "hour": local_dt.strftime("%H:%M"),
                "fee": "",  # V8: always empty in V1
                "approval": "",  # V8: always empty in V1
            }
        )

    return {
        "items": rows,
        "meta": make_pagination_meta(
            pagination.page,
            pagination.per_page,
            total_items,
            sort="trip_datetime_utc_asc,id_asc",
        ),
    }
