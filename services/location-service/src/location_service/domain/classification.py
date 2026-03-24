"""Domain logic for classification of segments (Section 5.4, 5.5, 5.6)."""

from decimal import ROUND_HALF_UP, Decimal

from location_service.enums import GradeClass, RoadClass, SpeedBand


def calculate_grade(start_elevation: float | None, end_elevation: float | None, distance_m: float) -> float | None:
    """Calculate point-to-point grade percentage.

    Formula: ((end_elevation - start_elevation) / distance_m) * 100
    Returns exactly to 2 decimal places.
    """
    if start_elevation is None or end_elevation is None or distance_m <= 0:
        return None

    grade = ((end_elevation - start_elevation) / distance_m) * 100
    return float(Decimal(grade).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def assign_grade_class(grade_pct: float | None) -> GradeClass:
    """Assign an enumerated GradeClass based on grade percentage."""
    if grade_pct is None:
        return GradeClass.FLAT

    if grade_pct <= -8.0:
        return GradeClass.DOWNHILL_STEEP
    if grade_pct <= -3.0:
        return GradeClass.DOWNHILL_MODERATE
    if grade_pct < 3.0:
        return GradeClass.FLAT
    if grade_pct < 8.0:
        return GradeClass.UPHILL_MODERATE

    return GradeClass.UPHILL_STEEP


def assign_speed_band(speed_limit: int | None, unit: str = "kph") -> SpeedBand:
    """Assign an enumerated SpeedBand based on speed limit in KPH or MPH."""
    if speed_limit is None:
        return SpeedBand.UNKNOWN

    limit_kph = speed_limit
    if unit.lower() == "mph":
        limit_kph = int(speed_limit * 1.60934)

    if limit_kph < 50:
        return SpeedBand.BAND_0_49
    if limit_kph < 80:
        return SpeedBand.BAND_50_79

    return SpeedBand.BAND_80_PLUS


def map_road_class(mapbox_class: str) -> RoadClass:
    """Map external Mapbox road classes to authoritative domain RoadClass enum."""
    class_map = {
        "motorway": RoadClass.MOTORWAY,
        "motorway_link": RoadClass.MOTORWAY_LINK,
        "trunk": RoadClass.TRUNK,
        "trunk_link": RoadClass.TRUNK_LINK,
        "primary": RoadClass.PRIMARY,
        "primary_link": RoadClass.PRIMARY_LINK,
        "secondary": RoadClass.SECONDARY,
        "secondary_link": RoadClass.SECONDARY_LINK,
        "tertiary": RoadClass.TERTIARY,
        "tertiary_link": RoadClass.TERTIARY_LINK,
        "street": RoadClass.STREET,
        "residential": RoadClass.STREET,
        "unclassified": RoadClass.STREET,
        "service": RoadClass.SERVICE,
        "ferry": RoadClass.FERRY,
    }
    return class_map.get(mapbox_class.lower().strip(), RoadClass.OTHER)
