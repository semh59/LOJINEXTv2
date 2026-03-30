"""Import jobs API router for Driver Service (spec §3.12–3.13).

Endpoints:
  POST  /internal/v1/driver-import-jobs       — create import job
  GET   /internal/v1/driver-import-jobs/{id}   — get import job detail
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from driver_service.auth import AuthContext, admin_or_internal_auth_dependency
from driver_service.database import async_session_factory, get_session
from driver_service.enums import ImportJobStatus, ImportRowStatus
from driver_service.errors import (
    ProblemDetailError,
    driver_import_batch_too_large,
    driver_not_found,
)
from driver_service.models import (
    DriverImportJobModel,
    DriverImportJobRowModel,
    DriverModel,
)
from driver_service.normalization import build_full_name_search_key, normalize_phone
from driver_service.schemas import CreateImportJobRequest

logger = logging.getLogger("driver_service")
router = APIRouter(prefix="/internal/v1/driver-import-jobs", tags=["driver-import"])

MAX_IMPORT_BATCH = 5000


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_ulid() -> str:
    return str(ULID())


async def _process_import_job(
    job_id: str,
    rows_data: list[Any],
    actor_id: str,
    strict_mode: bool,
    *,
    session_override: AsyncSession | None = None,
) -> None:
    """Background task to process import rows."""
    if session_override:
        await _run_process_logic(session_override, job_id, rows_data, actor_id, strict_mode)
    else:
        async with async_session_factory() as session:
            await _run_process_logic(session, job_id, rows_data, actor_id, strict_mode)
            await session.commit()


async def _run_process_logic(
    session: AsyncSession,
    job_id: str,
    rows_data: list[Any],
    actor_id: str,
    strict_mode: bool,
) -> None:
    """Internal logic for processing import job."""
    now = _now_utc()
    success_count = 0
    fail_count = 0

    # Fetch the job to update status to RUNNING
    result = await session.execute(select(DriverImportJobModel).where(DriverImportJobModel.import_job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        logger.error("Import job %s not found in background task", job_id)
        return

    job.started_at_utc = now
    await session.flush()

    for idx, row_input in enumerate(rows_data, start=1):
        row_id = _new_ulid()
        row_record = DriverImportJobRowModel(
            import_row_id=row_id,
            import_job_id=job_id,
            row_no=idx,
            source_payload_json=row_input.model_dump_json(),
            row_status=ImportRowStatus.PENDING.value,
            created_at_utc=now,
        )

        try:
            # Phone normalization (BR-18: allow missing)
            phone_result = normalize_phone(row_input.phone, allow_missing=True)

            # Build search key
            search_key = build_full_name_search_key(row_input.full_name.strip())

            # BR-21: Inactive reason sentinel
            status = row_input.status
            inactive_reason = row_input.inactive_reason
            if status == "INACTIVE" and not inactive_reason:
                inactive_reason = "LEGACY_IMPORT_NO_REASON_PROVIDED"

            # Check for existing driver by company_driver_code
            existing = await session.execute(
                select(DriverModel).where(
                    DriverModel.company_driver_code == row_input.company_driver_code,
                    DriverModel.soft_deleted_at_utc.is_(None),
                )
            )
            existing_driver = existing.scalar_one_or_none()

            if existing_driver:
                # Update existing driver
                existing_driver.full_name = row_input.full_name.strip()
                existing_driver.full_name_search_key = search_key
                existing_driver.phone_raw = phone_result.phone_raw
                existing_driver.phone_e164 = phone_result.phone_e164
                existing_driver.phone_normalization_status = phone_result.status.value
                if row_input.telegram_user_id:
                    existing_driver.telegram_user_id = row_input.telegram_user_id.strip()
                existing_driver.license_class = row_input.license_class.strip()
                existing_driver.employment_start_date = row_input.employment_start_date
                existing_driver.employment_end_date = row_input.employment_end_date
                existing_driver.status = status
                existing_driver.inactive_reason = inactive_reason
                if row_input.note:
                    existing_driver.note = row_input.note
                existing_driver.row_version += 1
                existing_driver.updated_at_utc = now
                existing_driver.updated_by_actor_id = actor_id

                row_record.row_status = ImportRowStatus.UPDATED.value
                row_record.resolved_driver_id = existing_driver.driver_id
            else:
                # Create new driver
                driver_id = _new_ulid()
                driver = DriverModel(
                    driver_id=driver_id,
                    company_driver_code=row_input.company_driver_code.strip(),
                    full_name=row_input.full_name.strip(),
                    full_name_search_key=search_key,
                    phone_raw=phone_result.phone_raw,
                    phone_e164=phone_result.phone_e164,
                    phone_normalization_status=phone_result.status.value,
                    telegram_user_id=row_input.telegram_user_id.strip() if row_input.telegram_user_id else None,
                    license_class=row_input.license_class.strip(),
                    employment_start_date=row_input.employment_start_date,
                    employment_end_date=row_input.employment_end_date,
                    status=status,
                    inactive_reason=inactive_reason,
                    note=row_input.note,
                    row_version=1,
                    created_at_utc=now,
                    created_by_actor_id=actor_id,
                    updated_at_utc=now,
                    updated_by_actor_id=actor_id,
                )
                session.add(driver)

                row_record.row_status = ImportRowStatus.CREATED.value
                row_record.resolved_driver_id = driver_id

            success_count += 1

        except ProblemDetailError as exc:
            row_record.row_status = ImportRowStatus.FAILED.value
            row_record.error_code = exc.code
            row_record.error_message = exc.detail
            fail_count += 1
        except Exception as exc:
            row_record.row_status = ImportRowStatus.FAILED.value
            row_record.error_code = "DRIVER_IMPORT_ROW_ERROR"
            row_record.error_message = str(exc)
            fail_count += 1

        session.add(row_record)

    # Finalize job
    job.success_rows = success_count
    job.failed_rows = fail_count
    job.completed_at_utc = _now_utc()

    if fail_count == 0:
        job.status = ImportJobStatus.COMPLETED.value
    elif success_count == 0:
        job.status = ImportJobStatus.FAILED.value
    else:
        job.status = ImportJobStatus.PARTIAL_SUCCESS.value

    await session.flush()


# ---------------------------------------------------------------------------
# POST /internal/v1/driver-import-jobs — create
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_import_job(
    body: CreateImportJobRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(admin_or_internal_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create and asynchronously process a driver import job (spec §3.12).

    Legacy import rules:
      BR-02: company_driver_code required for import
      BR-18: phone may be missing or invalid
      BR-21: INACTIVE without reason → sentinel value
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
    await session.commit()

    # Enqueue background task
    background_tasks.add_task(
        _process_import_job,
        job_id=job_id,
        rows_data=body.rows,
        actor_id=auth.actor_id,
        strict_mode=body.strict_mode,
    )

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
