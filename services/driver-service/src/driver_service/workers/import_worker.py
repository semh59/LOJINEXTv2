"""Durable import worker for Driver Service."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from driver_service.config import settings
from driver_service.database import async_session_factory
from driver_service.enums import AuditActionType, ImportJobStatus, ImportRowStatus
from driver_service.errors import ProblemDetailError
from driver_service.models import (
    DriverAuditLogModel,
    DriverImportJobModel,
    DriverImportJobRowModel,
    DriverModel,
    DriverOutboxModel,
)
from driver_service.normalization import build_full_name_search_key, normalize_phone
from driver_service.serializers import serialize_driver_admin
from driver_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger("driver_service.import_worker")


async def run_import_worker() -> None:
    """Poll for PENDING/RUNNING import jobs and process them."""
    logger.info("Import worker started (poll_interval=%ds)", settings.maintenance_poll_interval_seconds)

    while True:
        try:
            async with async_session_factory() as session:
                # Record heartbeat
                await record_worker_heartbeat(session, "import_worker", status="RUNNING")
                await session.commit()

            async with async_session_factory() as session:
                await _process_pending_jobs(session)
        except asyncio.CancelledError:
            logger.info("Import worker cancelled")
            return
        except Exception:
            logger.exception("Import worker error")

        await asyncio.sleep(settings.maintenance_poll_interval_seconds)


async def _process_pending_jobs(session: AsyncSession) -> None:
    """Find and process PENDING import jobs."""
    # We look for PENDING jobs. We also look for RUNNING jobs that might have been stranded
    # (though in this version we don't have a timeout-based reclaim yet, just polling).
    query = (
        select(DriverImportJobModel)
        .where(DriverImportJobModel.status == ImportJobStatus.PENDING.value)
        .order_by(DriverImportJobModel.created_at_utc.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        return

    logger.info("Claimed import job %s", job.import_job_id)
    job.status = ImportJobStatus.RUNNING.value
    job.started_at_utc = datetime.now(timezone.utc)
    await session.commit()

    # Process the job in a new session to avoid long-running transaction issues
    async with async_session_factory() as proc_session:
        try:
            await _run_job_logic(proc_session, job.import_job_id)
            await proc_session.commit()
            logger.info("Completed import job %s", job.import_job_id)
        except Exception:
            logger.exception("Failed to process import job %s", job.import_job_id)
            # Mark job as FAILED
            async with async_session_factory() as fail_session:
                stmt = select(DriverImportJobModel).where(DriverImportJobModel.import_job_id == job.import_job_id)
                res = await fail_session.execute(stmt)
                job_to_fail = res.scalar_one()
                job_to_fail.status = ImportJobStatus.FAILED.value
                job_to_fail.completed_at_utc = datetime.now(timezone.utc)
                await fail_session.commit()


async def _run_job_logic(session: AsyncSession, job_id: str) -> None:
    """Execute the actual import logic for a specific job."""
    # Re-fetch job in current session
    result = await session.execute(select(DriverImportJobModel).where(DriverImportJobModel.import_job_id == job_id))
    job = result.scalar_one()

    # Fetch rows metadata (we expect rows to be created by the API)
    rows_query = (
        select(DriverImportJobRowModel)
        .where(DriverImportJobRowModel.import_job_id == job_id)
        .order_by(DriverImportJobRowModel.row_no.asc())
    )
    rows_result = await session.execute(rows_query)
    rows = rows_result.scalars().all()

    success_count = 0
    fail_count = 0
    now = datetime.now(timezone.utc)

    for row in rows:
        if row.row_status != ImportRowStatus.PENDING.value:
            continue

        try:
            # The payload is stored in the row record
            from driver_service.schemas import ImportRowInput

            row_data = ImportRowInput.model_validate_json(row.source_payload_json)

            # Phone normalization
            phone_result = normalize_phone(row_data.phone, allow_missing=True)
            search_key = build_full_name_search_key(row_data.full_name.strip())

            # BR-21: Inactive reason sentinel
            status = row_data.status
            inactive_reason = row_data.inactive_reason
            if status == "INACTIVE" and not inactive_reason:
                inactive_reason = "LEGACY_IMPORT_NO_REASON_PROVIDED"

            # Check for existing driver
            existing = await session.execute(
                select(DriverModel).where(
                    DriverModel.company_driver_code == row_data.company_driver_code,
                    DriverModel.soft_deleted_at_utc.is_(None),
                )
            )
            existing_driver = existing.scalar_one_or_none()

            if existing_driver:
                # Capture OLD snapshot
                old_snapshot = serialize_driver_admin(existing_driver)

                # Update existing
                existing_driver.full_name = row_data.full_name.strip()
                existing_driver.full_name_search_key = search_key
                existing_driver.phone_raw = phone_result.phone_raw
                existing_driver.phone_e164 = phone_result.phone_e164
                existing_driver.phone_normalization_status = phone_result.status.value
                if row_data.telegram_user_id:
                    existing_driver.telegram_user_id = row_data.telegram_user_id.strip()
                existing_driver.license_class = row_data.license_class.strip()
                existing_driver.employment_start_date = row_data.employment_start_date
                existing_driver.employment_end_date = row_data.employment_end_date
                existing_driver.status = status
                existing_driver.inactive_reason = inactive_reason
                if row_data.note:
                    existing_driver.note = row_data.note
                existing_driver.row_version += 1
                existing_driver.updated_at_utc = now
                existing_driver.updated_by_actor_id = job.created_by_actor_id

                # Capture NEW snapshot
                new_snapshot = serialize_driver_admin(existing_driver)

                # Write Audit
                audit = DriverAuditLogModel(
                    audit_id=str(ULID()),
                    driver_id=existing_driver.driver_id,
                    action_type=AuditActionType.UPDATE.value,
                    old_snapshot_json=json.dumps(old_snapshot),
                    new_snapshot_json=json.dumps(new_snapshot),
                    actor_id=job.created_by_actor_id,
                    actor_role="ADMIN",
                    reason="Bulk import update",
                    created_at_utc=now,
                )
                session.add(audit)

                # Write Outbox
                outbox = DriverOutboxModel(
                    outbox_id=str(ULID()),
                    driver_id=existing_driver.driver_id,
                    event_name="driver.updated.v1",
                    event_version=1,
                    payload_json=json.dumps(
                        {
                            "driver_id": existing_driver.driver_id,
                            "row_version": existing_driver.row_version,
                            "updated_at_utc": now.isoformat(),
                        }
                    ),
                    publish_status="PENDING",
                    retry_count=0,
                    created_at_utc=now,
                    next_attempt_at_utc=now,
                )
                session.add(outbox)

                row.row_status = ImportRowStatus.UPDATED.value
                row.resolved_driver_id = existing_driver.driver_id
            else:
                # Create new
                driver_id = str(ULID())
                driver = DriverModel(
                    driver_id=driver_id,
                    company_driver_code=row_data.company_driver_code.strip(),
                    full_name=row_data.full_name.strip(),
                    full_name_search_key=search_key,
                    phone_raw=phone_result.phone_raw,
                    phone_e164=phone_result.phone_e164,
                    phone_normalization_status=phone_result.status.value,
                    telegram_user_id=row_data.telegram_user_id.strip() if row_data.telegram_user_id else None,
                    license_class=row_data.license_class.strip(),
                    employment_start_date=row_data.employment_start_date,
                    employment_end_date=row_data.employment_end_date,
                    status=status,
                    inactive_reason=inactive_reason,
                    note=row_data.note,
                    row_version=1,
                    created_at_utc=now,
                    created_by_actor_id=job.created_by_actor_id,
                    updated_at_utc=now,
                    updated_by_actor_id=job.created_by_actor_id,
                )
                session.add(driver)

                # Capture snapshot
                new_snapshot = serialize_driver_admin(driver)

                # Write Audit
                audit = DriverAuditLogModel(
                    audit_id=str(ULID()),
                    driver_id=driver.driver_id,
                    action_type=AuditActionType.CREATE.value,
                    new_snapshot_json=json.dumps(new_snapshot),
                    actor_id=job.created_by_actor_id,
                    actor_role="ADMIN",
                    reason="Bulk import creation",
                    created_at_utc=now,
                )
                session.add(audit)

                # Write Outbox
                outbox = DriverOutboxModel(
                    outbox_id=str(ULID()),
                    driver_id=driver_id,
                    event_name="driver.created.v1",
                    event_version=1,
                    payload_json=json.dumps(
                        {
                            "driver_id": driver_id,
                            "company_driver_code": driver.company_driver_code,
                            "phone_e164": driver.phone_e164,
                            "telegram_user_id": driver.telegram_user_id,
                            "license_class": driver.license_class,
                            "status": driver.status,
                            "row_version": driver.row_version,
                            "created_at_utc": now.isoformat(),
                        }
                    ),
                    publish_status="PENDING",
                    retry_count=0,
                    created_at_utc=now,
                    next_attempt_at_utc=now,
                )
                session.add(outbox)

                row.row_status = ImportRowStatus.CREATED.value
                row.resolved_driver_id = driver_id

            success_count += 1

        except ProblemDetailError as exc:
            row.row_status = ImportRowStatus.FAILED.value
            row.error_code = exc.code
            row.error_message = exc.detail
            fail_count += 1
        except Exception as exc:
            row.row_status = ImportRowStatus.FAILED.value
            row.error_code = "DRIVER_IMPORT_ROW_ERROR"
            row.error_message = str(exc)
            fail_count += 1

    # Finalize job
    job.success_rows = success_count
    job.failed_rows = fail_count
    job.completed_at_utc = datetime.now(timezone.utc)

    if fail_count == 0:
        job.status = ImportJobStatus.COMPLETED.value
    elif success_count == 0:
        job.status = ImportJobStatus.FAILED.value
    else:
        job.status = ImportJobStatus.PARTIAL_SUCCESS.value

    # Note: We should probably flush periodically if the job is very large,
    # but for now we follow the existing "one transaction per batch" pattern
    # unless Phase 3 requires more granularity.
