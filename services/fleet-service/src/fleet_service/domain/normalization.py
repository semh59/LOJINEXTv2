"""Plate normalization for Turkish license plates (Section 7, Gap #4).

Rules:
- Strip all whitespace and dashes
- ASCII uppercase
- Turkish İ → I, ı → I
- Reject empty or whitespace-only input
"""

from __future__ import annotations

import re


def normalize_plate(raw: str) -> str:
    """Normalize a raw license plate string.

    Args:
        raw: Raw plate input from user.

    Returns:
        Normalized plate string (uppercase, no whitespace/dashes).

    Raises:
        ValueError: If input is empty or whitespace-only.
    """
    if not raw or not raw.strip():
        raise ValueError("Plate cannot be empty or whitespace-only")

    # Turkish character normalization (İ→I, ı→I)
    normalized = raw.replace("İ", "I").replace("ı", "I")
    normalized = normalized.replace("i̇", "I")  # combined İ

    # ASCII uppercase
    normalized = normalized.upper()

    # Strip whitespace and dashes
    normalized = re.sub(r"[\s\-]+", "", normalized)

    if not normalized:
        raise ValueError("Plate cannot be empty after normalization")

    return normalized
