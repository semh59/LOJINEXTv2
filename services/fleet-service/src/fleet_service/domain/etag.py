"""Dual-stream ETag generation and parsing (Section 7.9).

Master ETag:  W/"vehicle-{id}-v{row_version}"
Spec ETag:    W/"vehicle-{id}-sv{spec_stream_version}"
"""

from __future__ import annotations

import re

_MASTER_ETAG_RE = re.compile(r'^W/"(vehicle|trailer)-([A-Za-z0-9]{26})-v(\d+)"$')
_SPEC_ETAG_RE = re.compile(r'^W/"(vehicle|trailer)-([A-Za-z0-9]{26})-sv(\d+)"$')


def generate_master_etag(asset_type: str, asset_id: str, row_version: int) -> str:
    """Generate a weak ETag for a master row mutation.

    Format: W/"vehicle-{id}-v{row_version}"
    """
    prefix = asset_type.lower()
    return f'W/"{prefix}-{asset_id}-v{row_version}"'


def generate_spec_etag(asset_type: str, asset_id: str, spec_stream_version: int) -> str:
    """Generate a weak ETag for a spec stream mutation.

    Format: W/"vehicle-{id}-sv{spec_stream_version}"
    """
    prefix = asset_type.lower()
    return f'W/"{prefix}-{asset_id}-sv{spec_stream_version}"'


def parse_master_etag(header: str) -> tuple[str, str, int] | None:
    """Parse a master ETag header.

    Returns (asset_type, asset_id, row_version) or None if invalid.
    """
    m = _MASTER_ETAG_RE.match(header)
    if not m:
        return None
    return m.group(1).upper(), m.group(2), int(m.group(3))


def parse_spec_etag(header: str) -> tuple[str, str, int] | None:
    """Parse a spec ETag header.

    Returns (asset_type, asset_id, spec_stream_version) or None if invalid.
    """
    m = _SPEC_ETAG_RE.match(header)
    if not m:
        return None
    return m.group(1).upper(), m.group(2), int(m.group(3))
