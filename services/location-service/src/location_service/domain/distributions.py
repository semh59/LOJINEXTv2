"""Domain logic for calculating segment distributions (Section 6.7)."""

from typing import Any, Sequence

from location_service.models import RouteSegment


def calculate_distributions(segments: Sequence[RouteSegment]) -> dict[str, dict[str, Any]]:
    """Calculate JSON distributions for road class, speed band, and urban density.

    Results are grouped by their enum string values, summing distance, then
    converting to a percentage of the total distance (rounded to 2 dp).

    Returns:
        {
            "road_type_distribution_json": {"HIGHWAY": 45.2, ...},
            "speed_limit_distribution_json": {"BAND_90_110": 80.0, ...},
            "urban_distribution_json": {"RURAL": 90.0, "URBAN": 10.0}
        }
    """
    total_dist = sum(s.distance_m for s in segments)
    if total_dist <= 0:
        return {
            "road_type_distribution_json": {},
            "speed_limit_distribution_json": {},
            "urban_distribution_json": {},
        }

    road_dist: dict[str, float] = {}
    speed_dist: dict[str, float] = {}
    urban_dist: dict[str, float] = {}

    for s in segments:
        road_val = s.road_class.value
        speed_val = s.speed_band.value
        urban_val = s.urban_class.value

        road_dist[road_val] = road_dist.get(road_val, 0.0) + s.distance_m
        speed_dist[speed_val] = speed_dist.get(speed_val, 0.0) + s.distance_m
        urban_dist[urban_val] = urban_dist.get(urban_val, 0.0) + s.distance_m

    def _to_pct(dist_map: dict[str, float]) -> dict[str, float]:
        pct_map = {k: round((v / total_dist) * 100, 2) for k, v in dist_map.items()}
        # Strip exact zero percentages if any occur through floating quirk
        return {k: v for k, v in pct_map.items() if v > 0}

    return {
        "road_type_distribution_json": _to_pct(road_dist),
        "speed_limit_distribution_json": _to_pct(speed_dist),
        "urban_distribution_json": _to_pct(urban_dist),
    }
