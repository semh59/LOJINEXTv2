"""Domain hashing for RFC 8785 strict payload hashing (Section 16 / 6.8)."""

import hashlib
from typing import Any

import canonicaljson


def _normalize_floats(obj: Any) -> Any:
    """Recursively convert floats to string with exact layout requirements.

    This ensures that payload signatures remain perfectly consistent
    across language boundaries and JSON serialization libraries.
    """
    if isinstance(obj, float):
        # Format strictly without scientific notation.
        return f"{obj:.6f}".rstrip("0").rstrip(".")
    if isinstance(obj, dict):
        return {k: _normalize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_floats(i) for i in obj]
    return obj


def draft_set_hash(payload: dict[str, Any]) -> str:
    """Compute strict RFC 8785 hash for approval/draft consistency.

    1. Normalizes float precision to string representation.
    2. Serializes dictionary using canonicaljson (RFC 8785).
    3. Returns SHA-256 hex digest.
    """
    normalized = _normalize_floats(payload)
    canon_bytes = canonicaljson.encode_canonical_json(normalized)
    return hashlib.sha256(canon_bytes).hexdigest()


def field_origin_matrix_hash(matrix: dict[str, Any]) -> str:
    """Compute consistent hash for field origin tracking matrices."""
    canon_bytes = canonicaljson.encode_canonical_json(matrix)
    return hashlib.sha256(canon_bytes).hexdigest()
