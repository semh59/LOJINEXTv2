"""Fleet timestamp helpers aligned with the current aware-UTC schema."""

from __future__ import annotations

import datetime


def utc_now_aware() -> datetime.datetime:
    """Return the current UTC timestamp as an aware datetime."""
    return datetime.datetime.now(datetime.UTC)


def to_utc_aware(timestamp: datetime.datetime | None) -> datetime.datetime | None:
    """Normalize an input timestamp to aware UTC."""
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=datetime.UTC)
    return timestamp.astimezone(datetime.UTC)
