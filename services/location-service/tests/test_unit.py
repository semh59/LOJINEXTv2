"""Unit tests for pure Python domain logic layer (Section 22)."""

import pytest

from location_service.domain.classification import (
    assign_grade_class,
    assign_speed_band,
    calculate_grade,
    map_road_class,
)
from location_service.domain.codes import generate_pair_code, generate_route_code
from location_service.domain.distributions import calculate_distributions
from location_service.domain.hashing import draft_set_hash, field_origin_matrix_hash
from location_service.domain.normalization import normalize_en, normalize_tr
from location_service.enums import DirectionCode, GradeClass, RoadClass, SpeedBand, UrbanClass
from location_service.models import RouteSegment


def test_normalization_tr_en_divergence() -> None:
    """Test dotless-i and dotted-i convergence rules for TR vs EN."""
    raw = "istanbul   ısparta Iğdır iğne-!!"

    # EN: straight upper, I remains I, i remains I.
    en_res = normalize_en(raw)
    assert en_res == "ISTANBUL ISPARTA IĞDIR IĞNE"

    # TR: i -> İ, I -> ı before upper -> İSTANBUL ISPARTA IĞDIR İĞNE
    tr_res = normalize_tr(raw)
    assert tr_res == "İSTANBUL ISPARTA IĞDIR İĞNE"


def test_normalization_punctuation_and_spaces() -> None:
    """Test regex strip and trim."""
    raw = "  Hello,    World!!! 123  "
    assert normalize_en(raw) == "HELLO WORLD 123"
    assert normalize_tr(raw) == "HELLO WORLD 123"


def test_codes_generation() -> None:
    """Test ULID pair code and direction suffixes."""
    pair_code = generate_pair_code()
    assert pair_code.startswith("RP_")
    assert len(pair_code) == 29  # 3 chars 'RP_' + 26 chars ULID

    route_f = generate_route_code(pair_code, DirectionCode.FORWARD)
    assert route_f == f"{pair_code}_F"

    route_r = generate_route_code(pair_code, DirectionCode.REVERSE)
    assert route_r == f"{pair_code}_R"


def test_calculate_grade() -> None:
    """Test grade percentage math."""
    assert calculate_grade(100.0, 110.0, 100.0) == 10.00
    assert calculate_grade(100.0, 90.0, 100.0) == -10.00
    assert calculate_grade(None, 110.0, 100.0) is None
    assert calculate_grade(100.0, 110.0, 0.0) is None

    # Test decimal rounding
    assert calculate_grade(100.0, 101.555, 100.0) == 1.56  # 1.555 -> 1.56


def test_assign_grade_class() -> None:
    """Test the 5-tier grade thresholds."""
    assert assign_grade_class(None) == GradeClass.FLAT
    assert assign_grade_class(2.9) == GradeClass.FLAT
    assert assign_grade_class(-2.9) == GradeClass.FLAT
    assert assign_grade_class(3.0) == GradeClass.UPHILL_MODERATE
    assert assign_grade_class(7.9) == GradeClass.UPHILL_MODERATE
    assert assign_grade_class(-3.0) == GradeClass.DOWNHILL_MODERATE
    assert assign_grade_class(-8.0) == GradeClass.DOWNHILL_STEEP
    assert assign_grade_class(8.0) == GradeClass.UPHILL_STEEP
    assert assign_grade_class(12.0) == GradeClass.UPHILL_STEEP


def test_assign_speed_band() -> None:
    """Test speed band assignment including MPH conversion."""
    assert assign_speed_band(None) == SpeedBand.UNKNOWN
    assert assign_speed_band(30, "kph") == SpeedBand.BAND_0_49
    assert assign_speed_band(49, "kph") == SpeedBand.BAND_0_49
    assert assign_speed_band(50, "kph") == SpeedBand.BAND_50_79
    assert assign_speed_band(79, "kph") == SpeedBand.BAND_50_79
    assert assign_speed_band(80, "kph") == SpeedBand.BAND_80_PLUS

    # 30 mph = ~48 kph -> BAND_0_49
    assert assign_speed_band(30, "mph") == SpeedBand.BAND_0_49
    # 70 mph = ~112 kph -> BAND_80_PLUS
    assert assign_speed_band(70, "mph") == SpeedBand.BAND_80_PLUS


def test_map_road_class() -> None:
    """Test mapbox road class mapping fallback."""
    assert map_road_class("motorway") == RoadClass.MOTORWAY
    assert map_road_class(" PRIMARY ") == RoadClass.PRIMARY
    assert map_road_class("unknown_fake") == RoadClass.OTHER


def test_draft_set_hash_formatting() -> None:
    """Test RFC 8785 float normalization."""
    payload_1 = {"distance": 12.345678, "nested": [10.000000, 0.0]}

    payload_2 = {"nested": [10.0, 0.0], "distance": 12.34567800001}
    hash1 = draft_set_hash(payload_1)
    hash2 = draft_set_hash(payload_2)

    assert hash1 == hash2


def test_calculate_distributions() -> None:
    """Test distribution percentage calculations."""
    segment_1 = RouteSegment(
        distance_m=100.0,
        road_class=RoadClass.MOTORWAY,
        speed_band=SpeedBand.BAND_80_PLUS,
        urban_class=UrbanClass.NON_URBAN,
    )
    segment_2 = RouteSegment(
        distance_m=300.0,
        road_class=RoadClass.MOTORWAY,
        speed_band=SpeedBand.BAND_80_PLUS,
        urban_class=UrbanClass.NON_URBAN,
    )
    segment_3 = RouteSegment(
        distance_m=100.0,
        road_class=RoadClass.STREET,
        speed_band=SpeedBand.BAND_0_49,
        urban_class=UrbanClass.URBAN,
    )

    dists = calculate_distributions([segment_1, segment_2, segment_3])

    rt = dists["road_type_distribution_json"]
    assert rt[RoadClass.MOTORWAY.value] == 80.0
    assert rt[RoadClass.STREET.value] == 20.0

    sp = dists["speed_limit_distribution_json"]
    assert sp[SpeedBand.BAND_80_PLUS.value] == 80.0
    assert sp[SpeedBand.BAND_0_49.value] == 20.0

    ur = dists["urban_distribution_json"]
    assert ur[UrbanClass.NON_URBAN.value] == 80.0
    assert ur[UrbanClass.URBAN.value] == 20.0

    empty = calculate_distributions([])
    assert empty["road_type_distribution_json"] == {}


def test_normalization_empty() -> None:
    """Test empty string and None handling."""
    assert normalize_en("") == ""
    assert normalize_tr("") == ""


def test_codes_generation_invalid_direction() -> None:
    """Test invalid direction raises error."""
    with pytest.raises(ValueError):
        # We purposely pass an invalid string acting as an enum
        generate_route_code("RP_XXX", "FAKE_DIR")  # type: ignore


def test_draft_set_hash_fallback() -> None:
    """Test primitive fallback in normalize floats."""
    # A string should just return a string
    from location_service.domain.hashing import _normalize_floats

    assert _normalize_floats("test") == "test"


def test_field_origin_matrix_hash() -> None:
    """Test matrix hashing execution."""
    matrix = {"A1": "System", "B2": "User"}
    h = field_origin_matrix_hash(matrix)
    assert isinstance(h, str)
    assert len(h) == 64
