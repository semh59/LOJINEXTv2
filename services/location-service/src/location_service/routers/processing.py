"""Processing API endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.auth import super_admin_auth_dependency
from location_service.config import settings
from location_service.database import get_db
from location_service.enums import PairStatus, RunStatus, TriggerType
from location_service.errors import (
    processing_run_not_found,
    route_pair_already_active_use_refresh,
    route_pair_already_running,
    route_pair_not_active_use_calculate,
    route_pair_not_found,
    route_pair_pending_draft_exists,
    route_pair_soft_deleted,
    run_not_stuck,
)
from location_service.models import ProcessingRun, RoutePair
from location_service.processing.pipeline import trigger_processing
from location_service.query_contracts import build_order_by, resolve_pagination, resolve_sort
from location_service.schemas import (
    CalculateRequest,
    PaginationMeta,
    ProcessingRunListResponse,
    ProcessingRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/pairs", tags=["processing"])
public_router = APIRouter(prefix="/v1", tags=["processing"])

_ALLOWED_LIST_SORTS = {
    "created_at_utc:desc",
    "created_at_utc:asc",
    "updated_at_utc:desc",
    "updated_at_utc:asc",
}
_DEFAULT_LIST_SORT = "created_at_utc:desc"


async def _check_pair_and_guard(pair_id: str, db: AsyncSession) -> RoutePair:
    """Fetch pair and enforce common state guards for processing triggers."""
    pair = await db.get(RoutePair, pair_id)
    if pair is None:
        raise route_pair_not_found(str(pair_id))
    if pair.pair_status == PairStatus.SOFT_DELETED:
        raise route_pair_soft_deleted()

    active_run = (
        await db.execute(
            select(ProcessingRun).where(
                ProcessingRun.route_pair_id == pair_id,
                ProcessingRun.run_status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
            )
        )
    ).scalar_one_or_none()
    if active_run is not None:
        raise route_pair_already_running()
    return pair


async def _get_run_with_pair(db: AsyncSession, run_id: str) -> tuple[ProcessingRun, RoutePair]:
    row = (
        await db.execute(
            select(ProcessingRun, RoutePair)
            .join(RoutePair, RoutePair.route_pair_id == ProcessingRun.route_pair_id)
            .where(ProcessingRun.processing_run_id == run_id)
        )
    ).one_or_none()
    if row is None:
        raise processing_run_not_found(str(run_id))
    run, pair = row
    return run, pair


def _serialize_run(run: ProcessingRun, pair: RoutePair) -> ProcessingRunResponse:
    return ProcessingRunResponse(
        run_id=run.processing_run_id,
        pair_id=run.route_pair_id,
        pair_code=pair.pair_code,
        trigger_type=run.trigger_type,
        run_status=run.run_status,
        attempt_no=run.attempt_no,
        provider_mapbox_status=run.provider_mapbox_status,
        provider_ors_status=run.provider_ors_status,
        error_message=run.error_message,
        started_at_utc=run.started_at_utc,
        completed_at_utc=run.completed_at_utc,
        created_at_utc=run.created_at_utc,
        updated_at_utc=run.updated_at_utc,
    )


@router.post("/{pair_id}/calculate", status_code=status.HTTP_202_ACCEPTED, response_model=ProcessingRunResponse)
async def calculate_route_pair(
    pair_id: str = Path(...),
    request: CalculateRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ProcessingRunResponse:
    """Trigger normative calculation for a non-active pair."""
    del request
    pair = await _check_pair_and_guard(pair_id, db)
    if pair.pair_status == PairStatus.ACTIVE:
        raise route_pair_already_active_use_refresh()
    if pair.pending_forward_version_no is not None or pair.pending_reverse_version_no is not None:
        raise route_pair_pending_draft_exists()

    run_id = await trigger_processing(pair_id=pair_id, trigger_type=TriggerType.INITIAL_CALCULATE)
    run = await db.get(ProcessingRun, run_id)
    if run is None:
        raise processing_run_not_found(str(run_id))
    return _serialize_run(run, pair)


@router.post("/{pair_id}/refresh", status_code=status.HTTP_202_ACCEPTED, response_model=ProcessingRunResponse)
async def refresh_route_pair(
    pair_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> ProcessingRunResponse:
    """Trigger refresh for an ACTIVE pair."""
    pair = await _check_pair_and_guard(pair_id, db)
    if pair.pair_status != PairStatus.ACTIVE:
        raise route_pair_not_active_use_calculate()

    run_id = await trigger_processing(pair_id=pair_id, trigger_type=TriggerType.MANUAL_REFRESH)
    run = await db.get(ProcessingRun, run_id)
    if run is None:
        raise processing_run_not_found(str(run_id))
    return _serialize_run(run, pair)


@public_router.get("/processing-runs/{run_id}", response_model=ProcessingRunResponse)
@router.get("/processing-runs/{run_id}", response_model=ProcessingRunResponse)
async def get_processing_run(run_id: str = Path(...), db: AsyncSession = Depends(get_db)) -> ProcessingRunResponse:
    """Get status of a ProcessingRun."""
    run, pair = await _get_run_with_pair(db, run_id)
    return _serialize_run(run, pair)


@router.get("/{pair_id}/processing-runs", response_model=ProcessingRunListResponse)
async def list_pair_processing_runs(
    pair_id: str,
    db: AsyncSession = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int | None, Query(ge=1, le=100)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100, description="Deprecated alias for per_page.")] = None,
    run_status: Annotated[RunStatus | None, Query()] = None,
    trigger_type: Annotated[TriggerType | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    """List processing runs for a route pair."""
    pair = await db.get(RoutePair, pair_id)
    if pair is None:
        raise route_pair_not_found(str(pair_id))

    pagination = resolve_pagination(page=page, per_page=per_page, limit=limit)
    sort_contract = resolve_sort(sort=sort, allowed=_ALLOWED_LIST_SORTS, default=_DEFAULT_LIST_SORT)
    order_by = build_order_by(
        sort_contract,
        {
            "created_at_utc": ProcessingRun.created_at_utc,
            "updated_at_utc": ProcessingRun.updated_at_utc,
        },
    )

    stmt = select(ProcessingRun).where(ProcessingRun.route_pair_id == pair_id)
    if run_status is not None:
        stmt = stmt.where(ProcessingRun.run_status == run_status)
    if trigger_type is not None:
        stmt = stmt.where(ProcessingRun.trigger_type == trigger_type)

    total_items = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar() or 0
    total_pages = (total_items + pagination.per_page - 1) // pagination.per_page if total_items else 0
    runs = (
        (
            await db.execute(
                stmt.order_by(order_by, ProcessingRun.processing_run_id.desc())
                .offset(pagination.offset)
                .limit(pagination.per_page)
            )
        )
        .scalars()
        .all()
    )

    return {
        "data": [_serialize_run(run, pair) for run in runs],
        "meta": PaginationMeta(
            page=pagination.page,
            per_page=pagination.per_page,
            total_items=total_items,
            total_pages=total_pages,
            sort=sort_contract.token,
        ).model_dump(),
    }


@public_router.post(
    "/processing-runs/{run_id}/force-fail",
    status_code=status.HTTP_200_OK,
    response_model=ProcessingRunResponse,
    dependencies=[Depends(super_admin_auth_dependency)],
)
@router.post(
    "/processing-runs/{run_id}/force-fail",
    status_code=status.HTTP_200_OK,
    response_model=ProcessingRunResponse,
    dependencies=[Depends(super_admin_auth_dependency)],
)
async def force_fail_processing_run(
    run_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> ProcessingRunResponse:
    """Force-fail a stuck processing run once the SLA has elapsed."""
    run, pair = await _get_run_with_pair(db, run_id)

    if run.run_status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        return _serialize_run(run, pair)

    sla_reference = run.started_at_utc or run.created_at_utc
    if datetime.now(UTC) < sla_reference + timedelta(minutes=settings.run_stuck_sla_minutes):
        raise run_not_stuck()

    run.run_status = RunStatus.FAILED
    run.error_message = "Force failed via API"
    await db.commit()
    await db.refresh(run)
    return _serialize_run(run, pair)
