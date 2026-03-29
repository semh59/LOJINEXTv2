"""Normative processing pipeline for route calculation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import ProgrammingError

from location_service.config import settings
from location_service.database import async_session_factory
from location_service.domain.classification import (
    assign_grade_class,
    assign_speed_band,
    calculate_grade,
    map_road_class,
)
from location_service.domain.codes import generate_route_code
from location_service.domain.distributions import calculate_distributions
from location_service.domain.hashing import draft_set_hash
from location_service.enums import (
    DirectionCode,
    ProcessingStatus,
    RunStatus,
    SpeedLimitState,
    TriggerType,
    UrbanClass,
    ValidationResult,
)
from location_service.models import (
    LocationPoint,
    ProcessingRun,
    Route,
    RoutePair,
    RouteSegment,
    RouteVersion,
    RouteVersionCounter,
)
from location_service.providers.mapbox_directions import MapboxDirectionsClient, MapboxRouteResponse
from location_service.providers.mapbox_terrain import MapboxTerrainClient
from location_service.providers.ors_validation import ORSValidationClient

logger = logging.getLogger(__name__)


_background_tasks: set[asyncio.Task[None]] = set()


def _task_done_callback(task: asyncio.Task[None]) -> None:
    """Remove completed task from the strong-reference registry."""
    _background_tasks.discard(task)
    if not task.cancelled() and (exc := task.exception()):
        logger.error("Unhandled background task exception: %s", exc, exc_info=exc)


def _dispatch_processing_task(run_id: UUID, pair_id: UUID) -> None:
    """Dispatch a processing run and keep a strong task reference."""
    task = asyncio.create_task(_process_route_pair_safe(run_id, pair_id))
    task.add_done_callback(_task_done_callback)
    _background_tasks.add(task)


async def trigger_processing(
    pair_id: UUID,
    trigger_type: TriggerType | str = TriggerType.INITIAL_CALCULATE,
    run_id: UUID | None = None,
) -> UUID:
    """Create a ProcessingRun row and dispatch background execution."""
    run_uuid = run_id or uuid.uuid4()

    async with async_session_factory() as session:
        run = ProcessingRun(
            processing_run_id=run_uuid,
            route_pair_id=pair_id,
            trigger_type=trigger_type if isinstance(trigger_type, TriggerType) else TriggerType(trigger_type),
            run_status=RunStatus.QUEUED,
        )
        session.add(run)
        await session.commit()

    _dispatch_processing_task(run_uuid, pair_id)
    return run_uuid


async def recover_processing_runs() -> int:
    """Re-dispatch queued or stale running processing runs at startup."""
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(minutes=settings.run_stuck_sla_minutes)
    recovered: list[tuple[UUID, UUID]] = []

    try:
        async with async_session_factory() as session:
            runs = (
                await session.execute(
                    select(ProcessingRun).where(ProcessingRun.run_status.in_([RunStatus.QUEUED, RunStatus.RUNNING]))
                )
            ).scalars().all()

            for run in runs:
                started_or_created = run.started_at_utc or run.created_at_utc
                if run.run_status == RunStatus.QUEUED:
                    recovered.append((run.processing_run_id, run.route_pair_id))
                    continue
                if started_or_created <= stale_cutoff:
                    run.run_status = RunStatus.QUEUED
                    run.started_at_utc = None
                    recovered.append((run.processing_run_id, run.route_pair_id))

            await session.commit()
    except ProgrammingError as exc:
        if "processing_runs" in str(exc).lower():
            logger.warning("Skipping processing run recovery because the schema is not migrated yet")
            return 0
        raise

    for run_id, pair_id in recovered:
        _dispatch_processing_task(run_id, pair_id)

    if recovered:
        logger.info("Recovered %d queued/stale processing runs at startup", len(recovered))
    return len(recovered)


async def _process_route_pair_safe(run_id: UUID, pair_id: UUID) -> None:
    """Exception boundary wrapper for the background processing task."""
    try:
        await _process_route_pair(run_id, pair_id)
    except Exception as exc:
        logger.error("Processing failed for pair %s, run %s: %s", pair_id, run_id, exc, exc_info=True)
        async with async_session_factory() as session:
            await session.execute(
                update(ProcessingRun)
                .where(ProcessingRun.processing_run_id == run_id)
                .values(
                    run_status=RunStatus.FAILED,
                    error_message=str(exc)[:1024],
                    completed_at_utc=datetime.now(UTC),
                )
            )
            await session.commit()


def _validate_route(mb_resp: MapboxRouteResponse, ors_resp: Any) -> ValidationResult:
    """Validate Mapbox route against ORS data."""
    if ors_resp.status == "UNVALIDATED":
        return ValidationResult.UNVALIDATED
    if mb_resp.distance > 0 and ors_resp.distance > 0:
        delta = abs(mb_resp.distance - ors_resp.distance) / mb_resp.distance
        if delta > 0.20:
            return ValidationResult.FAIL
    return ValidationResult.PASS_


def _extract_speed_limit(maxspeed_entry: Any) -> int | None:
    """Extract a speed limit in km/h from Mapbox maxspeed annotations."""
    if not isinstance(maxspeed_entry, dict):
        return None
    if maxspeed_entry.get("unknown") is True:
        return None
    speed = maxspeed_entry.get("speed")
    unit = str(maxspeed_entry.get("unit", "km/h")).lower()
    if not isinstance(speed, (int, float)) or speed <= 0:
        return None
    if unit == "mph":
        return round(float(speed) * 1.60934)
    return round(float(speed))


def _generate_segments(
    enriched_coords: list[tuple[float, float, float]], annotations: dict[str, Any]
) -> tuple[list[RouteSegment], float]:
    """Convert coordinates and annotations into route segments and known-limit ratio."""
    distances = annotations.get("distance", [])
    speeds = annotations.get("speed", [])
    maxspeeds = annotations.get("maxspeed", [])

    segments: list[RouteSegment] = []
    known_distance = 0.0
    total_distance = 0.0

    for i in range(len(enriched_coords) - 1):
        lng1, lat1, elev1 = enriched_coords[i]
        lng2, lat2, elev2 = enriched_coords[i + 1]

        dist = float(distances[i]) if i < len(distances) else 0.0
        actual_speed_ms = float(speeds[i]) if i < len(speeds) else 0.0
        actual_speed_kph = actual_speed_ms * 3.6
        speed_limit = _extract_speed_limit(maxspeeds[i]) if i < len(maxspeeds) else None

        grade_val = calculate_grade(elev1, elev2, dist)
        grade_klass = assign_grade_class(grade_val)
        speed_band = assign_speed_band(actual_speed_kph)
        road_class = map_road_class("primary")
        speed_limit_state = SpeedLimitState.KNOWN if speed_limit is not None else SpeedLimitState.UNKNOWN

        seg = RouteSegment(
            segment_no=i + 1,
            start_longitude_6dp=lng1,
            start_latitude_6dp=lat1,
            start_elevation_m=elev1,
            end_longitude_6dp=lng2,
            end_latitude_6dp=lat2,
            end_elevation_m=elev2,
            distance_m=dist,
            grade_pct=grade_val or 0.0,
            grade_class=grade_klass,
            road_class=road_class,
            urban_class=UrbanClass.UNKNOWN,
            speed_limit_state=speed_limit_state,
            speed_limit_kph=speed_limit,
            speed_band=speed_band,
            tunnel_flag=False,
        )
        segments.append(seg)
        total_distance += dist
        if speed_limit is not None:
            known_distance += dist

    ratio = 0.0 if total_distance <= 0 else round(known_distance / total_distance, 4)
    return segments, ratio


async def _process_route_pair(run_id: UUID, pair_id: UUID) -> None:
    """Calculate both route directions, enrich them, and persist draft versions."""
    mapbox_client = MapboxDirectionsClient()
    terrain_client = MapboxTerrainClient()
    ors_client = ORSValidationClient()

    async with async_session_factory() as session:
        run = await session.get(ProcessingRun, run_id)
        if not run or run.run_status != RunStatus.QUEUED:
            return
        run.run_status = RunStatus.RUNNING
        run.started_at_utc = datetime.now(UTC)
        run.error_message = None
        await session.commit()

        pair = await session.get(RoutePair, pair_id)
        if pair is None:
            raise ValueError("Pair not found")

        origin = await session.get(LocationPoint, pair.origin_location_id)
        dest = await session.get(LocationPoint, pair.destination_location_id)
        if origin is None or dest is None:
            raise ValueError("Pair references missing location points")

    directions = [
        (origin, dest, DirectionCode.FORWARD),
        (dest, origin, DirectionCode.REVERSE),
    ]

    results: list[dict[str, Any]] = []
    for start_pt, end_pt, direction in directions:
        logger.info("Calling Mapbox for pair %s [%s]", pair_id, direction)
        mb_resp = await mapbox_client.get_route(
            origin_lng=float(start_pt.longitude_6dp),
            origin_lat=float(start_pt.latitude_6dp),
            dest_lng=float(end_pt.longitude_6dp),
            dest_lat=float(end_pt.latitude_6dp),
        )

        ors_resp = await ors_client.get_validation(
            origin_lng=float(start_pt.longitude_6dp),
            origin_lat=float(start_pt.latitude_6dp),
            dest_lng=float(end_pt.longitude_6dp),
            dest_lat=float(end_pt.latitude_6dp),
        )

        val_status = _validate_route(mb_resp, ors_resp)
        coords = mb_resp.geometry.coordinates
        if not coords:
            raise ValueError(f"No coordinates in Mapbox response for {direction}")

        enriched_coords = await terrain_client.enrich_coordinates(coords)
        segments, known_speed_limit_ratio = _generate_segments(enriched_coords, mb_resp.annotations)
        dist_meta = calculate_distributions(segments)

        results.append(
            {
                "direction": direction,
                "mb_resp": mb_resp,
                "val_status": val_status,
                "segments": segments,
                "dist_meta": dist_meta,
                "known_speed_limit_ratio": known_speed_limit_ratio,
            }
        )

    async with async_session_factory() as session:
        pair = await session.get(RoutePair, pair_id)
        if pair is None:
            return

        pending_versions: dict[DirectionCode, int] = {}
        pair_changed = False

        for result in results:
            dir_code = result["direction"]
            mb_resp = result["mb_resp"]
            val_status = result["val_status"]
            segments = result["segments"]
            dist_meta = result["dist_meta"]
            known_speed_limit_ratio = result["known_speed_limit_ratio"]

            route_stmt = select(Route).where(Route.route_pair_id == pair_id, Route.direction == dir_code)
            route = (await session.execute(route_stmt)).scalar_one_or_none()

            if route is None:
                route = Route(
                    route_id=uuid.uuid4(),
                    route_pair_id=pair_id,
                    route_code=generate_route_code(pair.pair_code, dir_code),
                    direction=dir_code,
                    created_by="SYSTEM",
                )
                session.add(route)
                await session.flush()

            if dir_code == DirectionCode.FORWARD and pair.forward_route_id != route.route_id:
                pair.forward_route_id = route.route_id
                pair_changed = True
            if dir_code == DirectionCode.REVERSE and pair.reverse_route_id != route.route_id:
                pair.reverse_route_id = route.route_id
                pair_changed = True

            counter_stmt = (
                select(RouteVersionCounter).where(RouteVersionCounter.route_id == route.route_id).with_for_update()
            )
            counter = (await session.execute(counter_stmt)).scalar_one_or_none()
            if counter is None:
                counter = RouteVersionCounter(route_id=route.route_id, next_version_no=1)
                session.add(counter)
                await session.flush()

            version_no = counter.next_version_no
            counter.next_version_no += 1
            pending_versions[dir_code] = version_no

            version_payload = {
                "distance": mb_resp.distance,
                "duration": mb_resp.duration,
                "segments_count": len(segments),
            }
            version_hash = draft_set_hash(version_payload)

            version = RouteVersion(
                route_id=route.route_id,
                version_no=version_no,
                processing_run_id=run_id,
                processing_status=ProcessingStatus.CALCULATED_DRAFT,
                total_distance_m=mb_resp.distance,
                total_duration_s=int(mb_resp.duration),
                segment_count=len(segments),
                validation_result=val_status,
                field_origin_matrix_hash=version_hash,
                field_origin_matrix_json=version_payload,
                road_type_distribution_json=dist_meta["road_type_distribution_json"],
                speed_limit_distribution_json=dist_meta["speed_limit_distribution_json"],
                urban_distribution_json=dist_meta["urban_distribution_json"],
                known_speed_limit_ratio=known_speed_limit_ratio,
                processing_algorithm_version="1.0",
                warnings_json=[],
            )
            session.add(version)
            await session.flush()

            for segment in segments:
                segment.route_id = route.route_id
                segment.version_no = version_no
                session.add(segment)

        next_forward = pending_versions.get(DirectionCode.FORWARD)
        next_reverse = pending_versions.get(DirectionCode.REVERSE)
        if pair.pending_forward_version_no != next_forward:
            pair.pending_forward_version_no = next_forward
            pair_changed = True
        if pair.pending_reverse_version_no != next_reverse:
            pair.pending_reverse_version_no = next_reverse
            pair_changed = True
        if pair_changed:
            pair.row_version += 1

        run = await session.get(ProcessingRun, run_id)
        if run is None:
            return
        run.run_status = RunStatus.SUCCEEDED
        run.completed_at_utc = datetime.now(UTC)
        run.error_message = None
        await session.commit()

    logger.info("Successfully processed bidirectional pair %s", pair_id)
