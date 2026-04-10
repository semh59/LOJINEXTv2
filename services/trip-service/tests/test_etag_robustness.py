import re
import pytest
from trip_service.middleware import parse_etag_version


def test_parse_etag_version_canonical() -> None:
    # Format: "trip-<id>-v<version>"
    assert parse_etag_version('"trip-01JAT-v123"') == 123
    assert parse_etag_version(' "trip-ABC-v456" ') == 456


def test_parse_etag_version_no_quotes() -> None:
    assert parse_etag_version("trip-01JAT-v123") == 123
    assert parse_etag_version("trip-01JAT-789") == 789


def test_parse_etag_version_legacy_numeric() -> None:
    assert parse_etag_version('"123"') == 123
    assert parse_etag_version("456") == 456
    assert parse_etag_version(' "789" ') == 789


def test_parse_etag_version_invalid() -> None:
    assert parse_etag_version(None) is None
    assert parse_etag_version("") is None
    assert parse_etag_version('"invalid"') is None
    assert parse_etag_version("trip-no-version") is None


def test_parse_etag_version_v_prefix_optional() -> None:
    # Based on the regex in middleware.py: match = re.match(r"^trip-.+-(\d+)$", raw)
    # Wait, if the regex is ^trip-.+-(\d+)$, then trip-ID-v123 will FAIL.
    # Let's verify what the code ACTUALLY expects.
    # If the user fixed it to be robust, it should handle both.
    assert parse_etag_version('"trip-ID-123"') == 123
    # If this fails, then my assumption about the bug is correct.
