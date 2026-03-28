"""Shared timezone parsing and conversion helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InvalidTimezoneError(ValueError):
    """Raised when an IANA timezone string cannot be resolved."""


def parse_timezone(value: str) -> ZoneInfo:
    """Resolve an IANA timezone name to a ZoneInfo instance."""
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise InvalidTimezoneError("Invalid timezone.") from exc


def validate_timezone_name(value: str) -> str:
    """Validate that the provided value is a valid IANA timezone name."""
    parse_timezone(value)
    return value


def parse_local_datetime(value: str) -> datetime:
    """Parse a local ISO datetime string without timezone information."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("trip_datetime_local must be a valid ISO 8601 datetime without timezone.") from exc
    if parsed.tzinfo is not None:
        raise ValueError("trip_datetime_local must not include timezone information.")
    return parsed


def local_datetime_to_utc(local_value: str, timezone: str) -> datetime:
    """Convert a naive local datetime string into UTC."""
    tz = parse_timezone(timezone)
    local_dt = parse_local_datetime(local_value).replace(tzinfo=tz)
    return local_dt.astimezone(UTC)


def calendar_date_range_to_utc(
    date_from: date | None,
    date_to: date | None,
    timezone: str,
) -> tuple[datetime | None, datetime | None]:
    """Convert local calendar-date bounds into a UTC half-open range."""
    tz = parse_timezone(timezone)

    utc_from: datetime | None = None
    utc_to: datetime | None = None

    if date_from is not None:
        utc_from = datetime.combine(date_from, time.min, tzinfo=tz).astimezone(UTC)
    if date_to is not None:
        utc_to = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)

    return utc_from, utc_to


def utc_to_local(dt_utc: datetime, timezone: str) -> datetime:
    """Convert a UTC datetime into the requested timezone."""
    return dt_utc.astimezone(parse_timezone(timezone))
