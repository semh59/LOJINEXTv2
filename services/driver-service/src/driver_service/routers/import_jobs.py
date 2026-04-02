"""Import jobs API router for Driver Service (spec §3.12–3.13).

Endpoints:
  POST  /internal/v1/driver-import-jobs       — create import job
  GET   /internal/v1/driver-import-jobs/{id}   — get import job detail
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from driver_service.auth import AuthContext, admin_or_internal_auth_dependency
from driver_service.database import get_session
from driver_service.enums import ImportJobStatus, ImportRowStatus
from driver_service.errors import (
    driver_import_batch_too_large,
    driver_not_found,
)
from driver_service.models import (
    DriverImportJobModel,
    DriverImportJobRowModel,
)
from driver_service.schemas import CreateImportJobRequest

logger = logging.getLogger("driver_service")
router = APIRouter(prefix="/internal/v1/driver-import-jobs", tags=["driver-import"])

MAX_IMPORT_BATCH = 5000


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_ulid() -> str:
    return str(ULID())


# ---------------------------------------------------------------------------
# POST /internal/v1/driver-import-jobs — create
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_import_job(
    body: CreateImportJobRequest,
    auth: AuthContext = Depends(admin_or_internal_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create and asynchronously process a driver import job (spec §3.12).

    Durable Worker Pattern:
      1. Create Job record (PENDING)
      2. Create all Row records (PENDING)
      3. Commit
      4. Polling worker picks it up
    """
    now = _now_utc()

    if len(body.rows) > MAX_IMPORT_BATCH:
        raise driver_import_batch_too_large(MAX_IMPORT_BATCH)

    job_id = _new_ulid()
    job = DriverImportJobModel(
        import_job_id=job_id,
        status=ImportJobStatus.PENDING.value,
        total_rows=len(body.rows),
        success_rows=0,
        failed_rows=0,
        strict_mode=body.strict_mode,
        created_by_actor_id=auth.actor_id,
        created_at_utc=now,
    )
    session.add(job)

    # Create rows immediately in the API call for durability
    for idx, row_input in enumerate(body.rows, start=1):
        row_id = _new_ulid()
        row_record = DriverImportJobRowModel(
            import_row_id=row_id,
            import_job_id=job_id,
            row_no=idx,
            source_payload_json=row_input.model_dump_json(),
            row_status=ImportRowStatus.PENDING.value,
            created_at_utc=now,
        )
        session.add(row_record)

    await session.commit()

    return {
        "import_job_id": job.import_job_id,
        "status": job.status,
        "total_rows": job.total_rows,
        "created_at_utc": job.created_at_utc.isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /internal/v1/driver-import-jobs/{import_job_id} — detail
# ---------------------------------------------------------------------------


@router.get("/{import_job_id}")
async def get_import_job(
    import_job_id: str,
    auth: AuthContext = Depends(admin_or_internal_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get import job detail with row-level results (spec §3.13)."""
    result = await session.execute(
        select(DriverImportJobModel).where(DriverImportJobModel.import_job_id == import_job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise driver_not_found(import_job_id)

    # Fetch rows
    rows_result = await session.execute(
        select(DriverImportJobRowModel)
        .where(DriverImportJobRowModel.import_job_id == import_job_id)
        .order_by(DriverImportJobRowModel.row_no.asc())
    )
    rows = rows_result.scalars().all()

    return {
        "import_job_id": job.import_job_id,
        "status": job.status,
        "total_rows": job.total_rows,
        "success_rows": job.success_rows,
        "failed_rows": job.failed_rows,
        "strict_mode": job.strict_mode,
        "created_at_utc": job.created_at_utc.isoformat(),
        "started_at_utc": job.started_at_utc.isoformat() if job.started_at_utc else None,
        "completed_at_utc": job.completed_at_utc.isoformat() if job.completed_at_utc else None,
        "rows": [
            {
                "import_row_id": r.import_row_id,
                "row_no": r.row_no,
                "row_status": r.row_status,
                "resolved_driver_id": r.resolved_driver_id,
                "error_code": r.error_code,
                "error_message": r.error_message,
            }
            for r in rows
        ],
    }
