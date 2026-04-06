"""Deep tests for timezone parsing and conversion helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from trip_service.timezones import (
    InvalidTimezoneError,
    calendar_date_range_to_utc,
    local_datetime_to_utc,
    parse_local_datetime,
    parse_timezone,
    utc_to_local,
    validate_timezone_name,
)

pytestmark = pytest.mark.unit


def test_parse_timezone_rejects_invalid_name() -> None:
    with pytest.raises(InvalidTimezoneError):
        parse_timezone("Bad/Timezone")


def test_validate_timezone_name_round_trips_valid_name() -> None:
    assert validate_timezone_name("Europe/Istanbul") == "Europe/Istanbul"


def test_parse_local_datetime_rejects_timezone_aware_string() -> None:
    with pytest.raises(ValueError, match="must not include timezone information"):
        parse_local_datetime("2026-04-05T10:30:00+03:00")


def test_local_datetime_to_utc_converts_naive_local_value() -> None:
    converted = local_datetime_to_utc("2026-04-05T10:30", "Europe/Istanbul")

    assert converted == datetime(2026, 4, 5, 7, 30, tzinfo=UTC)


def test_calendar_date_range_to_utc_builds_half_open_window() -> None:
    utc_from, utc_to = calendar_date_range_to_utc(date(2026, 4, 5), date(2026, 4, 6), "Europe/Istanbul")

    assert utc_from == datetime(2026, 4, 4, 21, 0, tzinfo=UTC)
    assert utc_to == datetime(2026, 4, 6, 21, 0, tzinfo=UTC)


def test_utc_to_local_handles_dst_boundary_roundtrip() -> None:
    original = datetime(2026, 3, 29, 1, 30, tzinfo=UTC)

    local_value = utc_to_local(original, "Europe/Berlin")

    assert local_value.isoformat() == "2026-03-29T03:30:00+02:00"
    assert local_value.astimezone(UTC) == original
