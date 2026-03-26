"""Processing API endpoints (Section 7)."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db
from location_service.enums import PairStatus, RunStatus
from location_service.errors import (
    processing_run_not_found,
    route_pair_already_running,
    route_pair_not_found,
    route_pair_pending_draft_exists,
    route_pair_soft_deleted,
    run_not_stuck,
)
from location_service.models import ProcessingRun, RoutePair
from location_service.processing.pipeline import trigger_processing
from location_service.schemas import CalculateRequest, ProcessingRunResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/pairs", tags=["Processing"])

# SLA: A run must be stuck for at least this many minutes before force-fail is allowed
FORCE_FAIL_SLA_MINUTES = 30


async def _check_pair_and_guard(pair_id: UUID, db: AsyncSession) -> RoutePair:
    """Fetch pair and enforce common state guards for processing triggers."""
    pair = await db.get(RoutePair, pair_id)
    if not pair:
        raise route_pair_not_found(str(pair_id))

    # FINDING-09: Guard against SOFT_DELETED pair
    if pair.pair_status == PairStatus.SOFT_DELETED:
        raise route_pair_soft_deleted()

    # FINDING-09: Guard against concurrent QUEUED/RUNNING run (BR-04)
    active_run_stmt = select(ProcessingRun).where(
        ProcessingRun.route_pair_id == pair_id,
        ProcessingRun.run_status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
    )
    active_run = (await db.execute(active_run_stmt)).scalar_one_or_none()
    if active_run:
        raise route_pair_already_running()

    return pair


@router.post(
    "/{pair_id}/calculate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ProcessingRunResponse,
)
async def calculate_route_pair(
    pair_id: UUID = Path(...),
    request: CalculateRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ProcessingRunResponse:
    """Trigger normative calculation for a draft pair."""
    pair = await _check_pair_and_guard(pair_id, db)

    # FINDING-09: BR-03 — Cannot re-calculate if pending draft already exists
    if pair.pending_forward_version_no is not None:
        raise route_pair_pending_draft_exists()

    run_uuid = await trigger_processing(pair_id=pair_id, trigger_type="MANUAL")

    run = await db.get(ProcessingRun, run_uuid)
    if not run:
        raise processing_run_not_found(str(run_uuid))

    return ProcessingRunResponse.model_validate(run)


@router.post(
    "/{pair_id}/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ProcessingRunResponse,
)
async def refresh_route_pair(
    pair_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
) -> ProcessingRunResponse:
    """Trigger background refresh for an active pair."""
    await _check_pair_and_guard(pair_id, db)

    run_uuid = await trigger_processing(pair_id=pair_id, trigger_type="REFRESH")

    run = await db.get(ProcessingRun, run_uuid)
    return ProcessingRunResponse.model_validate(run)


@router.get(
    "/processing-runs/{run_id}",
    response_model=ProcessingRunResponse,
)
async def get_processing_run(
    run_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
) -> ProcessingRunResponse:
    """Get status of a ProcessingRun."""
    run = await db.get(ProcessingRun, run_id)
    if not run:
        raise processing_run_not_found(str(run_id))
    return ProcessingRunResponse.model_validate(run)


@router.post(
    "/processing-runs/{run_id}/force-fail",
    status_code=status.HTTP_200_OK,
    response_model=ProcessingRunResponse,
)
async def force_fail_processing_run(
    run_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
) -> ProcessingRunResponse:
    """Force-fail a stuck processing run (SLA must be exceeded)."""
    run = await db.get(ProcessingRun, run_id)
    if not run:
        raise processing_run_not_found(str(run_id))

    if run.run_status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        return ProcessingRunResponse.model_validate(run)

    # FINDING-10: Enforce SLA before allowing force-fail
    sla_reference = run.started_at_utc or run.created_at_utc
    sla_deadline = sla_reference + timedelta(minutes=FORCE_FAIL_SLA_MINUTES)
    if datetime.now(UTC) < sla_deadline:
        raise run_not_stuck()

    run.run_status = RunStatus.FAILED
    run.error_message = "Force failed via API"
    await db.commit()
    await db.refresh(run)

    return ProcessingRunResponse.model_validate(run)
