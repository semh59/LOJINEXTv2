"""SQLSTATE constraint error mapper (Section 12.4).

Maps PostgreSQL integrity violation codes to domain errors:
- SQLSTATE 23P01 (exclusion_violation) → SpecVersionOverlapError
- SQLSTATE 23505 (unique_violation) on spec_current → SpecVersionOverlapError
- SQLSTATE 23505 on plate → PlateAlreadyExistsError
- SQLSTATE 23505 on asset_code → AssetCodeAlreadyExistsError
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError

from fleet_service.errors import (
    ProblemDetailError,
    SpecVersionOverlapError,
    TrailerAssetCodeAlreadyExistsError,
    TrailerPlateAlreadyExistsError,
    VehicleAssetCodeAlreadyExistsError,
    VehiclePlateAlreadyExistsError,
)

logger = logging.getLogger("fleet_service.constraint_error_mapper")


def map_integrity_error(exc: IntegrityError, aggregate_type: str = "VEHICLE") -> ProblemDetailError:
    """Map a SQLAlchemy IntegrityError to the appropriate domain error.

    Args:
        exc: The SQLAlchemy IntegrityError.
        aggregate_type: "VEHICLE" or "TRAILER" to determine error type.

    Returns:
        A ProblemDetailError subclass.
    """
    orig = str(exc.orig) if exc.orig else ""
    pg_code = getattr(exc.orig, "pgcode", None) or ""

    logger.warning("IntegrityError (pgcode=%s): %s", pg_code, orig)

    # SQLSTATE 23P01 — exclusion constraint violation (spec window overlap)
    if pg_code == "23P01":
        return SpecVersionOverlapError()

    # SQLSTATE 23505 — unique constraint violation
    if pg_code == "23505":
        # Spec current unique index
        if "ux_fleet_vehicle_spec_current" in orig or "ux_fleet_trailer_spec_current" in orig:
            return SpecVersionOverlapError()

        # Plate unique index
        if "ux_fleet_vehicles_plate_live" in orig:
            return VehiclePlateAlreadyExistsError()
        if "ux_fleet_trailers_plate_live" in orig:
            return TrailerPlateAlreadyExistsError()

        # Asset code unique index
        if "ux_fleet_vehicles_asset_code" in orig:
            return VehicleAssetCodeAlreadyExistsError()
        if "ux_fleet_trailers_asset_code" in orig:
            return TrailerAssetCodeAlreadyExistsError()

        # Spec version_no uniqueness (also overlap)
        if "ux_fleet_vehicle_spec_no" in orig or "ux_fleet_trailer_spec_no" in orig:
            return SpecVersionOverlapError()

    # Fallback: re-raise as unknown
    logger.error("Unmapped IntegrityError (pgcode=%s): %s", pg_code, orig)
    raise exc
