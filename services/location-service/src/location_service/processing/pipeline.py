"""Normative processing pipeline for route calculation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from ulid import ULID

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
    RoadClass,
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


async def trigger_processing(
    pair_id: str,
    trigger_type: TriggerType | str = TriggerType.INITIAL_CALCULATE,
    run_id: str | None = None,
) -> str:
    """Create a ProcessingRun row and leave execution to the dedicated worker."""
    run_uuid = run_id or str(ULID())

    async with async_session_factory() as session:
        run = ProcessingRun(
            processing_run_id=run_uuid,
            route_pair_id=pair_id,
            trigger_type=trigger_type if isinstance(trigger_type, TriggerType) else TriggerType(trigger_type),
            run_status=RunStatus.QUEUED,
        )
        session.add(run)
        await session.commit()

    return run_uuid


def _clear_claim(run: ProcessingRun) -> None:
    """Clear claim fields once a run reaches a terminal state."""
    run.claim_token = None
    run.claim_expires_at_utc = None
    run.claimed_by_worker = None


async def mark_processing_run_failed(
    run_id: str,
    error_message: str,
    *,
    claim_token: str | None = None,
) -> None:
    """Persist a terminal FAILED status for the given processing run."""
    async with async_session_factory() as session:
        if claim_token is None:
            run = await session.get(ProcessingRun, run_id)
            if run is None:
                return
        else:
            stmt = select(ProcessingRun).where(
                ProcessingRun.processing_run_id == run_id,
                ProcessingRun.claim_token == claim_token,
            )
            run = (await session.execute(stmt)).scalar_one_or_none()
            if run is None:
                return

        run.run_status = RunStatus.FAILED
        run.error_message = error_message[:1024]
        run.completed_at_utc = datetime.now(UTC)
        _clear_claim(run)
        await session.commit()


@dataclass(frozen=True)
class ValidationSummary:
    """Persistable route-validation result and its supporting deltas."""

    validation_result: ValidationResult
    distance_validation_delta_pct: float | None
    duration_validation_delta_pct: float | None


@dataclass(frozen=True)
class SegmentMetadata:
    """Metadata applied to a route segment from the latest matching intersection."""

    road_class: RoadClass
    urban_class: UrbanClass
    tunnel_flag: bool


_DEFAULT_SEGMENT_METADATA = SegmentMetadata(
    road_class=RoadClass.OTHER,
    urban_class=UrbanClass.UNKNOWN,
    tunnel_flag=False,
)


def _delta_pct(primary_value: float, comparison_value: float) -> float | None:
    """Return the absolute percent-point delta when both values are positive."""
    if primary_value <= 0 or comparison_value <= 0:
        return None
    return round(abs(primary_value - comparison_value) / primary_value * 100.0, 3)


def _validate_route(mb_resp: MapboxRouteResponse, ors_resp: Any) -> ValidationSummary:
    """Validate Mapbox route against ORS distance and duration thresholds."""
    if ors_resp.status == "UNVALIDATED":
        return ValidationSummary(
            validation_result=ValidationResult.UNVALIDATED,
            distance_validation_delta_pct=None,
            duration_validation_delta_pct=None,
        )

    distance_delta_pct = _delta_pct(float(mb_resp.distance), float(ors_resp.distance))
    duration_delta_pct = _delta_pct(float(mb_resp.duration), float(ors_resp.duration))

    result = ValidationResult.PASS_
    if distance_delta_pct is not None and distance_delta_pct >= settings.distance_delta_fail_pct:
        result = ValidationResult.FAIL
    if duration_delta_pct is not None and duration_delta_pct >= settings.duration_delta_fail_pct:
        result = ValidationResult.FAIL
    if result != ValidationResult.FAIL:
        if distance_delta_pct is not None and distance_delta_pct >= settings.distance_delta_warning_pct:
            result = ValidationResult.WARNING
        if duration_delta_pct is not None and duration_delta_pct >= settings.duration_delta_warning_pct:
            result = ValidationResult.WARNING

    return ValidationSummary(
        validation_result=result,
        distance_validation_delta_pct=distance_delta_pct,
        duration_validation_delta_pct=duration_delta_pct,
    )


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


def _segment_metadata_from_intersection(intersection: dict[str, Any]) -> SegmentMetadata:
    """Map a Mapbox intersection object onto segment metadata defaults."""
    streets = intersection.get("mapbox_streets_v8")
    road_class_value = None
    if isinstance(streets, dict):
        road_class_value = streets.get("class")

    is_urban = intersection.get("is_urban")
    if is_urban is True:
        urban_class = UrbanClass.URBAN
    elif is_urban is False:
        urban_class = UrbanClass.NON_URBAN
    else:
        urban_class = UrbanClass.UNKNOWN

    classes = intersection.get("classes")
    tunnel_flag = False
    if isinstance(classes, list):
        tunnel_flag = any(str(item).strip().lower() == "tunnel" for item in classes)
    if not tunnel_flag and intersection.get("tunnel_name"):
        tunnel_flag = True

    return SegmentMetadata(
        road_class=map_road_class(str(road_class_value)) if road_class_value is not None else RoadClass.OTHER,
        urban_class=urban_class,
        tunnel_flag=tunnel_flag,
    )


def _segment_metadata_by_index(segment_count: int, legs: list[dict[str, Any]]) -> list[SegmentMetadata]:
    """Resolve the latest known intersection metadata for each segment index."""
    if segment_count <= 0:
        return []

    markers: list[tuple[int, SegmentMetadata]] = []
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        for step in leg.get("steps", []):
            if not isinstance(step, dict):
                continue
            for intersection in step.get("intersections", []):
                if not isinstance(intersection, dict):
                    continue
                geometry_index = intersection.get("geometry_index")
                if isinstance(geometry_index, int):
                    markers.append((geometry_index, _segment_metadata_from_intersection(intersection)))

    if not markers:
        return [_DEFAULT_SEGMENT_METADATA] * segment_count

    markers.sort(key=lambda item: item[0])
    metadata_by_index: list[SegmentMetadata] = []
    latest = _DEFAULT_SEGMENT_METADATA
    cursor = 0

    for segment_index in range(segment_count):
        while cursor < len(markers) and markers[cursor][0] <= segment_index:
            latest = markers[cursor][1]
            cursor += 1
        metadata_by_index.append(latest)

    return metadata_by_index


def _generate_segments(
    enriched_coords: list[tuple[float, float, float]],
    annotations: dict[str, Any],
    legs: list[dict[str, Any]],
) -> tuple[list[RouteSegment], float]:
    """Convert coordinates and annotations into route segments and known-limit ratio."""
    distances = annotations.get("distance", [])
    speeds = annotations.get("speed", [])
    maxspeeds = annotations.get("maxspeed", [])

    segments: list[RouteSegment] = []
    known_distance = 0.0
    total_distance = 0.0
    metadata_by_index = _segment_metadata_by_index(max(len(enriched_coords) - 1, 0), legs)

    for i in range(len(enriched_coords) - 1):
        lng1, lat1, elev1 = enriched_coords[i]
        lng2, lat2, elev2 = enriched_coords[i + 1]

        dist = float(distances[i]) if i < len(distances) else 0.0
        actual_speed_ms = float(speeds[i]) if i < len(speeds) else 0.0
        actual_speed_kph = actual_speed_ms * 3.6
        speed_limit = _extract_speed_limit(maxspeeds[i]) if i < len(maxspeeds) else None

        grade_val = calculate_grade(elev1, elev2, dist)
        grade_klass = assign_grade_class(grade_val)
        speed_band = assign_speed_band(round(actual_speed_kph) if actual_speed_kph > 0 else None)
        speed_limit_state = SpeedLimitState.KNOWN if speed_limit is not None else SpeedLimitState.UNKNOWN
        metadata = metadata_by_index[i] if i < len(metadata_by_index) else _DEFAULT_SEGMENT_METADATA

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
            road_class=metadata.road_class,
            urban_class=metadata.urban_class,
            speed_limit_state=speed_limit_state,
            speed_limit_kph=speed_limit,
            speed_band=speed_band,
            tunnel_flag=metadata.tunnel_flag,
        )
        segments.append(seg)
        total_distance += dist
        if speed_limit is not None:
            known_distance += dist

    ratio = 0.0 if total_distance <= 0 else round(known_distance / total_distance, 4)

    # Contiguity invariant: segment_no must be 1..N with no gaps.
    # This loop is the only writer — a gap here indicates a logic bug.
    expected = list(range(1, len(segments) + 1))
    actual = [s.segment_no for s in segments]
    if actual != expected:
        raise ValueError(f"Segment numbering is not contiguous: expected {expected}, got {actual}")

    return segments, ratio


async def _load_processing_context(
    run_id: str,
    pair_id: str,
    *,
    claim_token: str | None = None,
) -> tuple[LocationPoint, LocationPoint, RoutePair] | None:
    """Load the run and pair context needed for provider calls."""
    async with async_session_factory() as session:
        if claim_token is None:
            run = await session.get(ProcessingRun, run_id)
            if not run or run.route_pair_id != pair_id or run.run_status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                return None
            if run.run_status == RunStatus.QUEUED:
                run.run_status = RunStatus.RUNNING
                run.started_at_utc = datetime.now(UTC)
                run.error_message = None
                await session.commit()
        else:
            run = (
                await session.execute(
                    select(ProcessingRun).where(
                        ProcessingRun.processing_run_id == run_id,
                        ProcessingRun.route_pair_id == pair_id,
                        ProcessingRun.run_status == RunStatus.RUNNING,
                        ProcessingRun.claim_token == claim_token,
                    )
                )
            ).scalar_one_or_none()
            if run is None:
                return None

        pair = await session.get(RoutePair, pair_id)
        if pair is None:
            raise ValueError("Pair not found")

        origin = await session.get(LocationPoint, pair.origin_location_id)
        dest = await session.get(LocationPoint, pair.destination_location_id)
        if origin is None or dest is None:
            raise ValueError("Pair references missing location points")

    return origin, dest, pair


async def _process_route_pair(run_id: str, pair_id: str, *, claim_token: str | None = None) -> None:
    """Calculate both route directions, enrich them, and persist draft versions."""
    mapbox_client = MapboxDirectionsClient()
    terrain_client = MapboxTerrainClient()
    ors_client = ORSValidationClient()

    context = await _load_processing_context(run_id, pair_id, claim_token=claim_token)
    if context is None:
        return
    origin, dest, pair = context

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

        validation_summary = _validate_route(mb_resp, ors_resp)
        coords = mb_resp.geometry.coordinates
        if not coords:
            raise ValueError(f"No coordinates in Mapbox response for {direction}")

        enriched_coords = await terrain_client.enrich_coordinates(coords)
        segments, known_speed_limit_ratio = _generate_segments(enriched_coords, mb_resp.annotations, mb_resp.legs)
        dist_meta = calculate_distributions(segments)

        results.append(
            {
                "direction": direction,
                "mb_resp": mb_resp,
                "validation_summary": validation_summary,
                "segments": segments,
                "dist_meta": dist_meta,
                "known_speed_limit_ratio": known_speed_limit_ratio,
            }
        )

    async with async_session_factory() as session:
        pair_row = await session.get(RoutePair, pair_id)
        if pair_row is None:
            return
        pair = pair_row

        pending_versions: dict[DirectionCode, int] = {}
        pair_changed = False

        for result in results:
            dir_code = result["direction"]
            mb_resp = result["mb_resp"]
            validation_summary = result["validation_summary"]
            segments = result["segments"]
            dist_meta = result["dist_meta"]
            known_speed_limit_ratio = result["known_speed_limit_ratio"]

            route_stmt = select(Route).where(Route.route_pair_id == pair_id, Route.direction == dir_code)
            route = (await session.execute(route_stmt)).scalar_one_or_none()

            if route is None:
                route = Route(
                    route_id=str(ULID()),
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
                validation_result=validation_summary.validation_result,
                distance_validation_delta_pct=validation_summary.distance_validation_delta_pct,
                duration_validation_delta_pct=validation_summary.duration_validation_delta_pct,
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

        if claim_token is None:
            run = await session.get(ProcessingRun, run_id)
            if run is None:
                return
        else:
            stmt = select(ProcessingRun).where(
                ProcessingRun.processing_run_id == run_id,
                ProcessingRun.claim_token == claim_token,
            )
            run = (await session.execute(stmt)).scalar_one_or_none()
            if run is None:
                return
        run.run_status = RunStatus.SUCCEEDED
        run.completed_at_utc = datetime.now(UTC)
        run.error_message = None
        _clear_claim(run)
        await session.commit()

    logger.info("Successfully processed bidirectional pair %s", pair_id)
