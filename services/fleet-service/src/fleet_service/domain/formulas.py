"""Derived combination formulas for fuel-metadata resolve (Section 5).

Computes composite fields when vehicle + trailer specs are combined.
"""

from __future__ import annotations

from decimal import Decimal

from fleet_service.domain.enums import AeroPackageLevel


def combined_empty_weight_kg(
    vehicle_curb_weight_kg: Decimal | None,
    trailer_tare_weight_kg: Decimal | None,
    has_trailer: bool,
) -> Decimal | None:
    """Compute combined empty weight.

    - Both present and non-null → sum
    - Either null → result null
    - Trailer absent → vehicle curb_weight_kg (may be null)
    """
    if not has_trailer:
        return vehicle_curb_weight_kg
    if vehicle_curb_weight_kg is not None and trailer_tare_weight_kg is not None:
        return vehicle_curb_weight_kg + trailer_tare_weight_kg
    return None


def combined_axle_count(
    vehicle_total_axle_count: int | None,
    trailer_axle_count: int | None,
    has_trailer: bool,
) -> int | None:
    """Compute combined axle count.

    - Both present → sum
    - Either null → result null
    - Trailer absent → vehicle total_axle_count
    """
    if not has_trailer:
        return vehicle_total_axle_count
    if vehicle_total_axle_count is not None and trailer_axle_count is not None:
        return vehicle_total_axle_count + trailer_axle_count
    return None


def reefer_present(
    trailer_reefer_unit_present: bool | None,
    has_trailer: bool,
) -> bool:
    """Compute reefer_present.

    - Trailer present → trailer.reefer_unit_present (False if None)
    - No trailer → False
    """
    if not has_trailer:
        return False
    return bool(trailer_reefer_unit_present)


def composite_aero_package_level(
    vehicle_aero: str | None,
    trailer_aero: str | None,
    has_trailer: bool,
) -> str | None:
    """Compute composite aero_package_level (max of ordering NONE < LOW < MEDIUM < HIGH).

    - Only vehicle → vehicle value
    - Both → max of non-null values
    - Both null → null
    """
    ordering = AeroPackageLevel.ordering()

    if not has_trailer:
        return vehicle_aero

    v_rank = ordering.get(AeroPackageLevel(vehicle_aero), -1) if vehicle_aero else -1
    t_rank = ordering.get(AeroPackageLevel(trailer_aero), -1) if trailer_aero else -1

    if v_rank < 0 and t_rank < 0:
        return None
    if v_rank < 0:
        return trailer_aero
    if t_rank < 0:
        return vehicle_aero

    return vehicle_aero if v_rank >= t_rank else trailer_aero
