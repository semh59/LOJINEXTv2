import pytest

from fleet_service.domain.normalization import normalize_plate


def test_normalize_plate_basic():
    assert normalize_plate("34 ABC 123") == "34ABC123"
    assert normalize_plate("34-ABC-123") == "34ABC123"
    assert normalize_plate("  34abc123  ") == "34ABC123"


def test_normalize_plate_turkish_characters():
    # İ -> I, ı -> I
    assert normalize_plate("34 İST 123") == "34IST123"
    assert normalize_plate("34 ıst 123") == "34IST123"
    assert normalize_plate("i̇st") == "IST"  # combined dot


def test_normalize_plate_case_insensitivity():
    assert normalize_plate("34 abc 123") == "34ABC123"
    assert normalize_plate("AbC-123") == "ABC123"


def test_normalize_plate_empty_input():
    with pytest.raises(ValueError, match="Plate cannot be empty"):
        normalize_plate("")
    with pytest.raises(ValueError, match="Plate cannot be empty"):
        normalize_plate("   ")


def test_normalize_plate_only_special_chars():
    with pytest.raises(ValueError, match="after normalization"):
        normalize_plate("---   ---")
