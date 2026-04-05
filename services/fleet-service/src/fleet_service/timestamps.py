"""Fleet timestamp helpers aligned with the current naive-UTC schema."""

from __future__ import annotations

import datetime


def utc_now_naive() -> datetime.datetime:
    """Return the current UTC timestamp as a naive datetime."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def to_utc_naive(timestamp: datetime.datetime) -> datetime.datetime:
    """Normalize an input timestamp to naive UTC."""
    if timestamp.tzinfo is None:
        return timestamp
    return timestamp.astimezone(datetime.UTC).replace(tzinfo=None)


def to_utc_aware(timestamp: datetime.datetime) -> datetime.datetime:
    """Normalize an input timestamp to timezone-aware UTC."""
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=datetime.UTC)
    return timestamp.astimezone(datetime.UTC)
