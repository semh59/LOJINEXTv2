"""Pair and route code generation utilities (Section 5.2 and 5.3)."""

import ulid

from location_service.enums import DirectionCode


def generate_pair_code() -> str:
    """Generate a unique route pair code in the format RP_<ULID>."""
    return f"RP_{ulid.new().str}"


def generate_route_code(pair_code: str, direction: DirectionCode) -> str:
    """Derive a route code from a pair code and its direction.

    Example:
        RP_01H1V... -> RP_01H1V..._F (FORWARD) or RP_01H1V..._R (REVERSE)
    """
    if direction == DirectionCode.FORWARD:
        suffix = "F"
    elif direction == DirectionCode.REVERSE:
        suffix = "R"
    else:
        raise ValueError(f"Unknown direction code: {direction}")

    return f"{pair_code}_{suffix}"
