"""Shared data-quality helpers for trip-like ingestion flows."""

from __future__ import annotations


def compute_data_quality_flag(source_type: str, ocr_confidence: float | None, route_resolved: bool) -> str:
    """Compute the canonical data-quality flag.

    Rules:
    - Manual/admin-like sources are always HIGH.
    - Telegram-like sources use OCR confidence and route resolution truth table.
    """
    if source_type in {"ADMIN_MANUAL", "EMPTY_RETURN_ADMIN", "EXCEL_IMPORT"}:
        return "HIGH"
    if ocr_confidence is not None and ocr_confidence >= 0.90 and route_resolved:
        return "HIGH"
    if ocr_confidence is not None and ocr_confidence >= 0.70:
        return "MEDIUM"
    if not route_resolved:
        return "MEDIUM"
    return "LOW"
