"""Normative Processing Pipeline (Section 6.9).

Implements the 30-step algorithm for calculating and enriching route pairs.
"""

import logging
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

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


async def trigger_processing(pair_id: UUID, trigger_type: str = "MANUAL", run_id: UUID | None = None) -> UUID:
    """Entry point from API. Creates ProcessingRun and dispatches to background."""
    run_uuid = run_id or uuid.uuid4()

    async with async_session_factory() as session:
        run = ProcessingRun(
            run_id=run_uuid,
            pair_id=pair_id,
            trigger_type=trigger_type,
            run_status=RunStatus.QUEUED,
        )
        session.add(run)
        await session.commit()

    # Ideally async task dispatch here. We'll simulate background by yielding to asyncio
    import asyncio

    asyncio.create_task(_process_route_pair_safe(run_uuid, pair_id))

    return run_uuid


async def _process_route_pair_safe(run_id: UUID, pair_id: UUID) -> None:
    """Exception boundary wrapper for background task."""
    try:
        await _process_route_pair(run_id, pair_id)
    except Exception as e:
        logger.error(f"Processing failed for pair {pair_id}, run {run_id}: {e}", exc_info=True)
        async with async_session_factory() as session:
            # Mark run as failed
            await session.execute(
                update(ProcessingRun)
                .where(ProcessingRun.run_id == run_id)
                .values(run_status=RunStatus.FAILED, error_message=str(e)[:1024])
            )
            await session.commit()


def _validate_route(mb_resp: MapboxRouteResponse, ors_resp: Any) -> ValidationResult:
    """Validate Mapbox route against ORS data."""
    if ors_resp.status == "UNVALIDATED":
        return ValidationResult.UNVALIDATED

    if mb_resp.distance > 0 and ors_resp.distance > 0:
        delta = abs(mb_resp.distance - ors_resp.distance) / mb_resp.distance
        if delta > 0.20:
            return ValidationResult.FAILED

    return ValidationResult.PASS_


def _generate_segments(
    enriched_coords: list[tuple[float, float, float]], annotations: dict[str, Any]
) -> list[RouteSegment]:
    """Helper to convert coordinates and annotations to RouteSegment objects."""
    distances = annotations.get("distance", [])
    speeds = annotations.get("speed", [])

    segments = []

    for i in range(len(enriched_coords) - 1):
        lng1, lat1, elev1 = enriched_coords[i]
        lng2, lat2, elev2 = enriched_coords[i + 1]

        dist = distances[i] if i < len(distances) else 0.0
        actual_speed_ms = speeds[i] if i < len(speeds) else 0.0
        actual_speed_kph = actual_speed_ms * 3.6

        grade_val = calculate_grade(elev1, elev2, dist)
        grade_klass = assign_grade_class(grade_val)
        speed_band = assign_speed_band(actual_speed_kph)
        road_class = map_road_class("primary")  # Fallback for now
        speed_limit = None  # TODO: Implement speed limit extraction from V8 spec Section 6.2

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
            speed_limit_state=SpeedLimitState.KNOWN if speed_limit else SpeedLimitState.UNKNOWN,
            speed_limit_kph=speed_limit,
            speed_band=speed_band,
            tunnel_flag=False,
        )
        segments.append(seg)

    return segments


async def _process_route_pair(run_id: UUID, pair_id: UUID) -> None:
    """The 30-step normative algorithm (Section 6.9)."""

    mapbox_client = MapboxDirectionsClient()
    terrain_client = MapboxTerrainClient()
    ors_client = ORSValidationClient()

    async with async_session_factory() as session:
        # Step 1-3: Lock Run and Update status
        run = await session.get(ProcessingRun, run_id)
        if not run or run.run_status != RunStatus.QUEUED:
            return
        run.run_status = RunStatus.RUNNING
        await session.commit()

        # Step 4: Fetch Pair and Locations
        pair = await session.get(RoutePair, pair_id)
        if not pair:
            raise ValueError("Pair not found")

        origin = await session.get(LocationPoint, pair.origin_location_id)
        dest = await session.get(LocationPoint, pair.destination_location_id)

    # Process Directions: Forward and Reverse
    directions = [
        (origin, dest, DirectionCode.FORWARD),
        (dest, origin, DirectionCode.REVERSE),
    ]

    results = []

    for start_pt, end_pt, direction in directions:
        # Step 5-8: Call Mapbox Driving Directions
        logger.info(f"Calling Mapbox for pair {pair_id} [{direction}]")
        mb_resp = await mapbox_client.get_route(
            origin_lng=start_pt.longitude_6dp,
            origin_lat=start_pt.latitude_6dp,
            dest_lng=end_pt.longitude_6dp,
            dest_lat=end_pt.latitude_6dp,
        )

        # Step 9-11: Call ORS and Validate
        ors_resp = await ors_client.get_validation(
            origin_lng=start_pt.longitude_6dp,
            origin_lat=start_pt.latitude_6dp,
            dest_lng=end_pt.longitude_6dp,
            dest_lat=end_pt.latitude_6dp,
        )

        val_status = _validate_route(mb_resp, ors_resp)

        # Step 12-14: Extract Points and Fetch Elev
        coords = mb_resp.geometry.get("coordinates", [])
        if not coords:
            raise ValueError(f"No coordinates in mapbox response for {direction}")

        enriched_coords = await terrain_client.enrich_coordinates(coords)

        # Step 15-22: Extract segments
        segments = _generate_segments(enriched_coords, mb_resp.annotations)

        # Step 23: Distributions
        dist_meta = calculate_distributions(segments)

        results.append(
            {
                "direction": direction,
                "mb_resp": mb_resp,
                "val_status": val_status,
                "segments": segments,
                "dist_meta": dist_meta,
            }
        )

    # Step 24-30: Atomic Database TX
    async with async_session_factory() as session:
        pair = await session.get(RoutePair, pair_id)
        if not pair:
            return

        for res in results:
            dir_code = res["direction"]
            mb_resp = res["mb_resp"]
            val_status = res["val_status"]
            segments = res["segments"]
            dist_meta = res["dist_meta"]

            # 1. Get or Create Route
            route_stmt = select(Route).where(Route.route_pair_id == pair_id, Route.direction == dir_code)
            route = (await session.execute(route_stmt)).scalar_one_or_none()

            if not route:
                route = Route(
                    route_id=uuid.uuid4(),
                    route_pair_id=pair_id,
                    route_code=generate_route_code(pair.pair_code, dir_code),
                    direction=dir_code,
                    created_by="SYSTEM",
                )
                session.add(route)
                await session.flush()

            # 2. Increment version
            counter_stmt = (
                select(RouteVersionCounter).where(RouteVersionCounter.route_id == route.route_id).with_for_update()
            )
            counter = (await session.execute(counter_stmt)).scalar_one_or_none()
            if not counter:
                counter = RouteVersionCounter(route_id=route.route_id, next_version_no=1)
                session.add(counter)
                await session.flush()

            version_no = counter.next_version_no
            counter.next_version_no += 1

            # 3. Create Version
            # Payload for hashing (simplified version of segments + summary)
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
                known_speed_limit_ratio=0.0,  # Placeholder
                processing_algorithm_version="1.0",
                warnings_json=[],
            )
            session.add(version)
            await session.flush()

            # 4. Save Segments
            for s in segments:
                s.route_id = route.route_id
                s.version_no = version_no
                session.add(s)

            # 5. Link to Pair (Pending Draft)
            if dir_code == DirectionCode.FORWARD:
                pair.pending_forward_version_no = version_no
            else:
                pair.pending_reverse_version_no = version_no

        # Update run status
        run = await session.get(ProcessingRun, run_id)
        run.run_status = RunStatus.SUCCEEDED
        await session.commit()

    logger.info(f"Successfully processed bidirectional pair {pair_id}")
