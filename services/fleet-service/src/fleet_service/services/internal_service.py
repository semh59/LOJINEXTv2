"""Internal service — business logic for service-to-service endpoints (Phase F).

All operations are read-only (no transactions, no outbox/timeline writes).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.clients import driver_client
from fleet_service.domain import formulas
from fleet_service.errors import (
    DependencyUnavailableError,
    TrailerNotFoundError,
    VehicleNotFoundError,
)
from fleet_service.models import (
    FleetTrailer,
    FleetTrailerSpecVersion,
    FleetVehicle,
    FleetVehicleSpecVersion,
)
from fleet_service.repositories import trailer_spec_repo, vehicle_spec_repo
from fleet_service.schemas.responses import (
    CursorResponse,
    DerivedCombination,
    FuelMetadataResolveResponse,
    FuelMetadataSpecResponse,
    FuelMetadataTrailerSpecResponse,
    SelectableItemResponse,
    ValidateBulkItemResponse,
    ValidateResponse,
)

logger = logging.getLogger("fleet_service.internal_service")


# === VALIDATE — SINGLE ===


async def validate_single(
    session: AsyncSession,
    asset_type: str,
    asset_id: str,
) -> ValidateResponse:
    """Validate a single vehicle or trailer — always returns 200.

    If asset not found → exists=False.
    """
    if asset_type.upper() == "VEHICLE":
        stmt = select(FleetVehicle).where(FleetVehicle.vehicle_id == asset_id)
        result = await session.execute(stmt)
        vehicle = result.scalar_one_or_none()
        if not vehicle:
            return ValidateResponse(exists=False)
        return ValidateResponse(
            exists=True,
            status=vehicle.status,
            lifecycle_state=vehicle.lifecycle_state,
            is_selectable=vehicle.is_selectable,
            is_usable_for_new_operation=vehicle.is_selectable,
            reason_code=_reason_code(vehicle.status, vehicle.soft_deleted_at_utc),
        )

    # TRAILER
    t_stmt = select(FleetTrailer).where(FleetTrailer.trailer_id == asset_id)
    t_result = await session.execute(t_stmt)
    trailer_obj = t_result.scalar_one_or_none()
    if not trailer_obj:
        return ValidateResponse(exists=False)
    return ValidateResponse(
        exists=True,
        status=trailer_obj.status,
        lifecycle_state=trailer_obj.lifecycle_state,
        is_selectable=trailer_obj.is_selectable,
        is_usable_for_new_operation=trailer_obj.is_selectable,
        reason_code=_reason_code(trailer_obj.status, trailer_obj.soft_deleted_at_utc),
    )


# === VALIDATE — BULK ===


async def validate_bulk(
    session: AsyncSession,
    vehicle_ids: list[str] | None,
    trailer_ids: list[str] | None,
) -> list[ValidateBulkItemResponse]:
    """Validate multiple vehicles and trailers in one call."""
    results: list[ValidateBulkItemResponse] = []

    if vehicle_ids:
        stmt = select(FleetVehicle).where(FleetVehicle.vehicle_id.in_(vehicle_ids))
        rows = await session.execute(stmt)
        found = {v.vehicle_id: v for v in rows.scalars()}
        for vid in vehicle_ids:
            v = found.get(vid)
            if not v:
                results.append(ValidateBulkItemResponse(asset_id=vid, asset_type="VEHICLE", exists=False))
            else:
                results.append(
                    ValidateBulkItemResponse(
                        asset_id=vid,
                        asset_type="VEHICLE",
                        exists=True,
                        status=v.status,
                        lifecycle_state=v.lifecycle_state,
                        is_selectable=v.is_selectable,
                        is_usable_for_new_operation=v.is_selectable,
                        reason_code=_reason_code(v.status, v.soft_deleted_at_utc),
                    )
                )

    if trailer_ids:
        t_stmt = select(FleetTrailer).where(FleetTrailer.trailer_id.in_(trailer_ids))
        t_rows = await session.execute(t_stmt)
        found_trailers = {t.trailer_id: t for t in t_rows.scalars()}
        for tid in trailer_ids:
            t_obj = found_trailers.get(tid)
            if not t_obj:
                results.append(ValidateBulkItemResponse(asset_id=tid, asset_type="TRAILER", exists=False))
            else:
                results.append(
                    ValidateBulkItemResponse(
                        asset_id=tid,
                        asset_type="TRAILER",
                        exists=True,
                        status=t_obj.status,
                        lifecycle_state=t_obj.lifecycle_state,
                        is_selectable=t_obj.is_selectable,
                        is_usable_for_new_operation=t_obj.is_selectable,
                        reason_code=_reason_code(t_obj.status, t_obj.soft_deleted_at_utc),
                    )
                )

    return results


# === VALIDATE — TRIP COMPAT ===


async def validate_trip_compat(
    session: AsyncSession,
    driver_id: str,
    vehicle_id: str,
    trailer_id: str | None = None,
) -> dict[str, Any]:
    """Validate driver + vehicle + optional trailer combo for trip creation.

    Calls driver-service for driver validation, validates vehicle/trailer locally.
    Returns combined compatibility result.
    """
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    # Driver check (remote)
    driver_ok = False
    try:
        driver_result = await driver_client.validate_driver(driver_id)
        if not driver_result.get("exists", False):
            errors.append({"field": "driver_id", "code": "DRIVER_NOT_FOUND"})
        elif not driver_result.get("is_usable_for_new_operation", False):
            errors.append(
                {
                    "field": "driver_id",
                    "code": "DRIVER_NOT_SELECTABLE",
                    "reason": driver_result.get("reason_code", "UNKNOWN"),
                }
            )
        else:
            driver_ok = True
    except DependencyUnavailableError:
        warnings.append({"field": "driver_id", "code": "DRIVER_SERVICE_UNAVAILABLE"})
        driver_ok = True  # Optimistic — allow trip with warning

    # Vehicle check (local)
    vehicle_resp = await validate_single(session, "VEHICLE", vehicle_id)
    if not vehicle_resp.exists:
        errors.append({"field": "vehicle_id", "code": "VEHICLE_NOT_FOUND"})
    elif not vehicle_resp.is_usable_for_new_operation:
        errors.append(
            {"field": "vehicle_id", "code": "VEHICLE_NOT_SELECTABLE", "reason": vehicle_resp.reason_code or "UNKNOWN"}
        )

    # Trailer check (local, optional)
    if trailer_id:
        trailer_resp = await validate_single(session, "TRAILER", trailer_id)
        if not trailer_resp.exists:
            errors.append({"field": "trailer_id", "code": "TRAILER_NOT_FOUND"})
        elif not trailer_resp.is_usable_for_new_operation:
            errors.append(
                {
                    "field": "trailer_id",
                    "code": "TRAILER_NOT_SELECTABLE",
                    "reason": trailer_resp.reason_code or "UNKNOWN",
                }
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "driver_ok": driver_ok,
        "vehicle_exists": vehicle_resp.exists if vehicle_resp else False,
    }


async def validate_trip_compat_contract(
    session: AsyncSession,
    driver_id: str,
    vehicle_id: str | None,
    trailer_id: str | None = None,
) -> dict[str, Any]:
    """Validate trip references against the live Driver and Fleet contracts.

    This is the recovery-time contract returned to trip-service. It keeps the
    canonical `driver_valid` / `vehicle_valid` / `trailer_valid` fields while
    preserving a couple of legacy aliases during the transition.
    """
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    driver_valid = False
    vehicle_valid: bool | None = None
    trailer_valid: bool | None = None

    try:
        driver_result = await driver_client.validate_driver(driver_id)
        if not driver_result.get("exists", False):
            errors.append({"field": "driver_id", "code": "DRIVER_NOT_FOUND"})
        elif not driver_result.get("is_assignable", False):
            errors.append(
                {
                    "field": "driver_id",
                    "code": "DRIVER_NOT_ASSIGNABLE",
                    "reason": str(driver_result.get("status") or "UNKNOWN"),
                }
            )
        else:
            driver_valid = True
    except DependencyUnavailableError:
        warnings.append({"field": "driver_id", "code": "DRIVER_SERVICE_UNAVAILABLE"})
        driver_valid = True  # Optimistic fallback consistent with validate_trip_compat

    if vehicle_id is not None:
        vehicle_resp = await validate_single(session, "VEHICLE", vehicle_id)
        if not vehicle_resp.exists:
            errors.append({"field": "vehicle_id", "code": "VEHICLE_NOT_FOUND"})
            vehicle_valid = False
        elif not vehicle_resp.is_usable_for_new_operation:
            errors.append(
                {
                    "field": "vehicle_id",
                    "code": "VEHICLE_NOT_SELECTABLE",
                    "reason": vehicle_resp.reason_code or "UNKNOWN",
                }
            )
            vehicle_valid = False
        else:
            vehicle_valid = True

    if trailer_id:
        trailer_resp = await validate_single(session, "TRAILER", trailer_id)
        if not trailer_resp.exists:
            errors.append({"field": "trailer_id", "code": "TRAILER_NOT_FOUND"})
            trailer_valid = False
        elif not trailer_resp.is_usable_for_new_operation:
            errors.append(
                {
                    "field": "trailer_id",
                    "code": "TRAILER_NOT_SELECTABLE",
                    "reason": trailer_resp.reason_code or "UNKNOWN",
                }
            )
            trailer_valid = False
        else:
            trailer_valid = True

    valid = not errors
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "driver_valid": driver_valid,
        "vehicle_valid": vehicle_valid,
        "trailer_valid": trailer_valid,
    }


# === SELECTABLE — VEHICLES ===


async def list_selectable_vehicles(
    session: AsyncSession,
    *,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> CursorResponse:
    """Get selectable vehicles (is_selectable=true), cursor-paginated."""
    stmt = select(FleetVehicle).where(FleetVehicle.is_selectable.is_(True)).order_by(FleetVehicle.vehicle_id)

    if q:
        like_q = f"%{q}%"
        stmt = stmt.where(FleetVehicle.normalized_plate_current.ilike(like_q) | FleetVehicle.asset_code.ilike(like_q))
    if cursor:
        stmt = stmt.where(FleetVehicle.vehicle_id > cursor)

    stmt = stmt.limit(limit + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars())

    has_more = len(rows) > limit
    items = rows[:limit]

    return CursorResponse(
        items=[
            SelectableItemResponse(
                asset_id=v.vehicle_id,
                asset_code=v.asset_code,
                plate_raw_current=v.plate_raw_current,
                normalized_plate_current=v.normalized_plate_current,
                brand=v.brand,
                model=v.model,
                model_year=v.model_year,
            )
            for v in items
        ],
        next_cursor=items[-1].vehicle_id if has_more and items else None,
        has_more=has_more,
    )


# === SELECTABLE — TRAILERS ===


async def list_selectable_trailers(
    session: AsyncSession,
    *,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> CursorResponse:
    """Get selectable trailers (is_selectable=true), cursor-paginated."""
    stmt = select(FleetTrailer).where(FleetTrailer.is_selectable.is_(True)).order_by(FleetTrailer.trailer_id)

    if q:
        like_q = f"%{q}%"
        stmt = stmt.where(FleetTrailer.normalized_plate_current.ilike(like_q) | FleetTrailer.asset_code.ilike(like_q))
    if cursor:
        stmt = stmt.where(FleetTrailer.trailer_id > cursor)

    stmt = stmt.limit(limit + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars())

    has_more = len(rows) > limit
    items = rows[:limit]

    return CursorResponse(
        items=[
            SelectableItemResponse(
                asset_id=t.trailer_id,
                asset_code=t.asset_code,
                plate_raw_current=t.plate_raw_current,
                normalized_plate_current=t.normalized_plate_current,
                brand=t.brand,
                model=t.model,
                model_year=t.model_year,
            )
            for t in items
        ],
        next_cursor=items[-1].trailer_id if has_more and items else None,
        has_more=has_more,
    )


# === FUEL METADATA — RESOLVE ===


async def resolve_fuel_metadata(
    session: AsyncSession,
    vehicle_id: str,
    trailer_id: str | None = None,
    at: datetime.datetime | None = None,
) -> FuelMetadataResolveResponse:
    """Resolve fuel-metadata for vehicle (+ optional trailer) at a point-in-time.

    - If `at` is None → get current spec.
    - Computes derived combination formulas from `formulas.py`.
    """
    # Vehicle spec
    v_spec: FleetVehicleSpecVersion | None
    if at:
        v_spec = await vehicle_spec_repo.get_spec_as_of(session, vehicle_id, at)
    else:
        v_spec = await vehicle_spec_repo.get_current_spec(session, vehicle_id)

    if not v_spec:
        raise VehicleNotFoundError(vehicle_id)

    vehicle_meta = FuelMetadataSpecResponse(
        fuel_type=v_spec.fuel_type,
        powertrain_type=v_spec.powertrain_type,
        emission_class=v_spec.emission_class,
        engine_power_kw=v_spec.engine_power_kw,
        curb_weight_kg=v_spec.curb_weight_kg,
        gvwr_kg=v_spec.gvwr_kg,
        aero_package_level=v_spec.aero_package_level,
        tire_rr_class=v_spec.tire_rr_class,
    )

    # Trailer spec (optional)
    trailer_meta: FuelMetadataTrailerSpecResponse | None = None
    t_spec: FleetTrailerSpecVersion | None = None
    has_trailer = trailer_id is not None

    if trailer_id:
        if at:
            t_spec = await trailer_spec_repo.get_spec_as_of(session, trailer_id, at)
        else:
            t_spec = await trailer_spec_repo.get_current_spec(session, trailer_id)

        if not t_spec:
            raise TrailerNotFoundError(trailer_id)

        trailer_meta = FuelMetadataTrailerSpecResponse(
            trailer_type=t_spec.trailer_type,
            tare_weight_kg=t_spec.tare_weight_kg,
            max_payload_kg=t_spec.max_payload_kg,
            axle_count=t_spec.axle_count,
            aero_package_level=t_spec.aero_package_level,
            tire_rr_class=t_spec.tire_rr_class,
            reefer_unit_present=t_spec.reefer_unit_present,
            reefer_unit_type=t_spec.reefer_unit_type,
            reefer_power_source=t_spec.reefer_power_source,
        )

    # Derived combination
    derived = DerivedCombination(
        combined_empty_weight_kg=formulas.combined_empty_weight_kg(
            v_spec.curb_weight_kg,
            t_spec.tare_weight_kg if t_spec else None,
            has_trailer,
        ),
        combined_axle_count=formulas.combined_axle_count(
            v_spec.total_axle_count,
            t_spec.axle_count if t_spec else None,
            has_trailer,
        ),
        reefer_present=formulas.reefer_present(
            t_spec.reefer_unit_present if t_spec else None,
            has_trailer,
        ),
        aero_package_level=formulas.composite_aero_package_level(
            v_spec.aero_package_level,
            t_spec.aero_package_level if t_spec else None,
            has_trailer,
        ),
    )

    return FuelMetadataResolveResponse(
        vehicle=vehicle_meta,
        trailer=trailer_meta,
        derived_combination=derived,
    )


# === HELPERS ===


def _reason_code(status: str, soft_deleted_at: datetime.datetime | None) -> str | None:
    """Derive reason_code for validate responses."""
    if soft_deleted_at is not None:
        return "SOFT_DELETED"
    if status == "INACTIVE":
        return "INACTIVE"
    return None
