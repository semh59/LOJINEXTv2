"""Idempotency utilities (Section 8.9).

endpoint_fingerprint: first 32 hex chars of SHA256("{METHOD}:{ROUTE}")
request_hash:         full hex SHA256 of canonical JSON
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_endpoint_fingerprint(method: str, path: str) -> str:
    """Compute endpoint_fingerprint = first 32 hex chars of SHA256("{METHOD}:{PATH}").

    Args:
        method: HTTP method (uppercase), e.g. "POST"
        path: Route template with leading slash, e.g. "/api/v1/vehicles"

    Returns:
        First 32 hex characters (128 bits) of SHA256 digest.
    """
    data = f"{method.upper()}:{path}"
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
    return digest[:32]


def compute_request_hash(body: dict[str, Any], dto_fields: list[str] | None = None) -> str:
    """Compute request_hash = SHA256 of canonical JSON.

    Canonical JSON rules (Section 8.9):
    1. Take parsed request body (all fields incl. optional).
    2. For every field defined in DTO: if absent, normalize to null.
    3. Recursively sort all object keys alphabetically.
    4. Serialize to UTF-8 JSON with no whitespace, null values retained.
    5. request_hash = hex(SHA256(canonical_utf8_json_bytes))

    Args:
        body: The parsed request body dict.
        dto_fields: Optional list of all DTO field names. If provided,
                     absent fields are normalized to null.

    Returns:
        Full hex SHA256 digest string.
    """
    normalized = dict(body)
    if dto_fields:
        for field in dto_fields:
            if field not in normalized:
                normalized[field] = None

    canonical = json.dumps(
        _sort_keys_recursive(normalized),
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sort_keys_recursive(obj: Any) -> Any:
    """Recursively sort dict keys for canonical serialization."""
    if isinstance(obj, dict):
        return {k: _sort_keys_recursive(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_sort_keys_recursive(item) for item in obj]
    return obj
