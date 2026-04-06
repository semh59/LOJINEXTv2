"""Internal route and trip-context endpoints for downstream services."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db
from location_service.domain.normalization import normalize_en, normalize_tr
from location_service.enums import PairStatus, ProcessingStatus
from location_service.errors import (
    route_ambiguous,
    route_pair_not_active_use_calculate,
    route_pair_not_found,
    route_pair_soft_deleted,
    route_resolution_not_found,
)
from location_service.models import LocationPoint, RoutePair, RouteVersion
from location_service.schemas import (
    InternalRouteResolveRequest,
    InternalRouteResolveResponse,
    InternalTripContextResponse,
    ProfileCode,
)

router = APIRouter(tags=["internal-routes"])


async def _find_point_ids_by_normalized_name(
    session: AsyncSession,
    *,
    normalized_origin: str,
    normalized_destination: str,
    use_english_names: bool,
) -> tuple[str | None, str | None]:
    """Resolve origin/destination point IDs by exact normalized names."""
    name_column = LocationPoint.normalized_name_en if use_english_names else LocationPoint.normalized_name_tr

    origin_id = (
        await session.execute(
            select(LocationPoint.location_id).where(name_column == normalized_origin, LocationPoint.is_active.is_(True))
        )
    ).scalar_one_or_none()
    destination_id = (
        await session.execute(
            select(LocationPoint.location_id).where(
                name_column == normalized_destination, LocationPoint.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    return origin_id, destination_id


async def _collect_active_route_candidates(
    session: AsyncSession,
    *,
    origin_location_id: str,
    destination_location_id: str,
    profile_code: str,
    resolution: Literal["EXACT_TR", "EXACT_EN"],
) -> list[InternalRouteResolveResponse]:
    """Collect all matching ACTIVE route-version candidates for a pair resolution attempt."""
    pairs = (
        (
            await session.execute(
                select(RoutePair).where(
                    RoutePair.profile_code == profile_code,
                    RoutePair.pair_status == PairStatus.ACTIVE,
                    or_(
                        and_(
                            RoutePair.origin_location_id == origin_location_id,
                            RoutePair.destination_location_id == destination_location_id,
                        ),
                        and_(
                            RoutePair.origin_location_id == destination_location_id,
                            RoutePair.destination_location_id == origin_location_id,
                        ),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )

    candidates: list[InternalRouteResolveResponse] = []
    for pair in pairs:
        if pair.origin_location_id == origin_location_id and pair.destination_location_id == destination_location_id:
            route_id = pair.forward_route_id
            version_no = pair.current_active_forward_version_no
        else:
            route_id = pair.reverse_route_id
            version_no = pair.current_active_reverse_version_no

        if route_id is None or version_no is None:
            continue

        active_version = (
            await session.execute(
                select(RouteVersion.route_id).where(
                    RouteVersion.route_id == route_id,
                    RouteVersion.version_no == version_no,
                    RouteVersion.processing_status == ProcessingStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()
        if active_version is None:
            continue

        candidates.append(
            InternalRouteResolveResponse(route_id=route_id, pair_id=pair.route_pair_id, resolution=resolution)
        )

    return candidates


@router.post("/internal/v1/routes/resolve", response_model=InternalRouteResolveResponse)
async def resolve_route(
    payload: InternalRouteResolveRequest,
    session: AsyncSession = Depends(get_db),
) -> InternalRouteResolveResponse:
    """Resolve an active route by exact normalized origin/destination names."""
    attempts: list[tuple[str, str, bool]] = []
    if payload.language_hint in {"AUTO", "TR"}:
        attempts.append((normalize_tr(payload.origin_name), normalize_tr(payload.destination_name), False))
    if payload.language_hint in {"AUTO", "EN"}:
        attempts.append((normalize_en(payload.origin_name), normalize_en(payload.destination_name), True))

    unique_candidates: dict[tuple[str, str], InternalRouteResolveResponse] = {}
    for normalized_origin, normalized_destination, use_english_names in attempts:
        origin_id, destination_id = await _find_point_ids_by_normalized_name(
            session,
            normalized_origin=normalized_origin,
            normalized_destination=normalized_destination,
            use_english_names=use_english_names,
        )
        if origin_id is None or destination_id is None:
            continue

        resolution: Literal["EXACT_TR", "EXACT_EN"] = "EXACT_EN" if use_english_names else "EXACT_TR"
        candidates = await _collect_active_route_candidates(
            session,
            origin_location_id=origin_id,
            destination_location_id=destination_id,
            profile_code=payload.profile_code,
            resolution=resolution,
        )
        for candidate in candidates:
            unique_candidates.setdefault((candidate.route_id, candidate.pair_id), candidate)

    if not unique_candidates:
        raise route_resolution_not_found()
    if len(unique_candidates) > 1:
        raise route_ambiguous()
    return next(iter(unique_candidates.values()))


@router.get("/internal/v1/route-pairs/{pair_id}/trip-context", response_model=InternalTripContextResponse)
async def get_trip_context(pair_id: str, session: AsyncSession = Depends(get_db)) -> InternalTripContextResponse:
    """Return forward and reverse trip context for an active route pair."""
    pair = await session.get(RoutePair, pair_id)
    if pair is None:
        raise route_pair_not_found(str(pair_id))
    if pair.pair_status == PairStatus.SOFT_DELETED:
        raise route_pair_soft_deleted()
    if pair.pair_status != PairStatus.ACTIVE:
        raise route_pair_not_active_use_calculate()
    if (
        pair.forward_route_id is None
        or pair.reverse_route_id is None
        or pair.current_active_forward_version_no is None
        or pair.current_active_reverse_version_no is None
    ):
        raise route_pair_not_active_use_calculate()

    origin = await session.get(LocationPoint, pair.origin_location_id)
    destination = await session.get(LocationPoint, pair.destination_location_id)
    if origin is None or destination is None:
        raise route_pair_not_found(str(pair_id))

    forward_version = (
        await session.execute(
            select(RouteVersion).where(
                RouteVersion.route_id == pair.forward_route_id,
                RouteVersion.version_no == pair.current_active_forward_version_no,
                RouteVersion.processing_status == ProcessingStatus.ACTIVE,
            )
        )
    ).scalar_one_or_none()
    reverse_version = (
        await session.execute(
            select(RouteVersion).where(
                RouteVersion.route_id == pair.reverse_route_id,
                RouteVersion.version_no == pair.current_active_reverse_version_no,
                RouteVersion.processing_status == ProcessingStatus.ACTIVE,
            )
        )
    ).scalar_one_or_none()
    if forward_version is None or reverse_version is None:
        raise route_pair_not_active_use_calculate()

    return InternalTripContextResponse(
        pair_id=pair.route_pair_id,
        origin_location_id=pair.origin_location_id,
        origin_name=origin.name_tr,
        destination_location_id=pair.destination_location_id,
        destination_name=destination.name_tr,
        forward_route_id=pair.forward_route_id,
        forward_duration_s=forward_version.total_duration_s,
        reverse_route_id=pair.reverse_route_id,
        reverse_duration_s=reverse_version.total_duration_s,
        profile_code=ProfileCode(pair.profile_code),
        pair_status=pair.pair_status,
    )
