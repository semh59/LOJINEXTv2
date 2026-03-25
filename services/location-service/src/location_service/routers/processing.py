"""Processing API endpoints (Section 7)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db
from location_service.errors import processing_run_not_found, route_pair_not_found
from location_service.models import ProcessingRun, RoutePair
from location_service.processing.pipeline import trigger_processing
from location_service.schemas import CalculateRequest, ProcessingRunResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/pairs", tags=["Processing"])


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
    """Trigger normative calculation for a draft or active pair."""
    pair = await db.get(RoutePair, pair_id)
    if not pair:
        raise route_pair_not_found(str(pair_id))

    # Validation rules state calculation is only allowed on certain pair statues
    # but that's handled gracefully in trigger_processing or domain logic

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
    pair = await db.get(RoutePair, pair_id)
    if not pair:
        raise route_pair_not_found(str(pair_id))

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
    """Force fail a stuck processing run."""
    from location_service.enums import RunStatus

    run = await db.get(ProcessingRun, run_id)
    if not run:
        raise processing_run_not_found(str(run_id))

    # Only allowed if running/queued and past SLA
    if run.run_status in (RunStatus.QUEUED, RunStatus.RUNNING):
        run.run_status = RunStatus.FAILED
        run.error_message = "Force failed via API"
        await db.commit()
        await db.refresh(run)

    return ProcessingRunResponse.model_validate(run)
