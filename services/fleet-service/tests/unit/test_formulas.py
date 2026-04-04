from decimal import Decimal

from fleet_service.domain.formulas import (
    combined_axle_count,
    combined_empty_weight_kg,
    composite_aero_package_level,
    reefer_present,
)


def test_combined_empty_weight_kg():
    v = Decimal("8000.00")
    t = Decimal("5000.00")

    # Trailer present
    assert combined_empty_weight_kg(v, t, True) == Decimal("13000.00")
    assert combined_empty_weight_kg(v, None, True) is None
    assert combined_empty_weight_kg(None, t, True) is None

    # Trailer absent
    assert combined_empty_weight_kg(v, t, False) == v
    assert combined_empty_weight_kg(None, t, False) is None


def test_combined_axle_count():
    v = 2
    t = 3

    # Trailer present
    assert combined_axle_count(v, t, True) == 5
    assert combined_axle_count(v, None, True) is None
    assert combined_axle_count(None, t, True) is None

    # Trailer absent
    assert combined_axle_count(v, t, False) == 2
    assert combined_axle_count(None, t, False) is None


def test_reefer_present():
    assert reefer_present(True, True) is True
    assert reefer_present(False, True) is False
    assert reefer_present(None, True) is False
    assert reefer_present(True, False) is False


def test_composite_aero_package_level():
    # Only vehicle
    assert composite_aero_package_level("HIGH", "LOW", False) == "HIGH"
    assert composite_aero_package_level(None, "LOW", False) is None

    # Both (max logic)
    assert composite_aero_package_level("LOW", "HIGH", True) == "HIGH"
    assert composite_aero_package_level("MEDIUM", "NONE", True) == "MEDIUM"
    assert composite_aero_package_level(None, "HIGH", True) == "HIGH"
    assert composite_aero_package_level("LOW", None, True) == "LOW"
    assert composite_aero_package_level(None, None, True) is None
