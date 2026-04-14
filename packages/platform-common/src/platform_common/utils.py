from datetime import datetime, UTC

def utc_now() -> datetime:
    """Standardized UTC now function across the platform."""
    return datetime.now(UTC)
