"""Canonical normalization algorithms (spec Appendix A).

A.1  Full-name search key: Turkish-aware lowercasing + transliteration.
A.2  Phone normalization: E.164 via phonenumbers library.
"""

from __future__ import annotations

import unicodedata

import phonenumbers

from driver_service.config import settings
from driver_service.enums import PhoneNormalizationStatus

# ---------------------------------------------------------------------------
# A.1  Full-name search key
# ---------------------------------------------------------------------------

# Turkish letter transliteration map (spec Appendix A.1)
_TURKISH_TRANSLITERATION: dict[str, str] = {
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "Ç": "c",
    "Ğ": "g",
    "İ": "i",
    "Ö": "o",
    "Ş": "s",
    "Ü": "u",
}

_TR_TRANS_TABLE = str.maketrans(_TURKISH_TRANSLITERATION)


def build_full_name_search_key(full_name: str) -> str:
    """Build a normalized search key from a display name (spec Appendix A.1).

    Algorithm:
      1. Unicode NFKC normalize
      2. Trim leading/trailing whitespace
      3. Collapse internal whitespace runs to single space
      4. Lowercase using Turkish-aware locale handling
      5. Transliterate Turkish letters to ASCII
      6. Remove repeated spaces if transformation introduces drift
    """
    # Step 1: NFKC normalize
    text = unicodedata.normalize("NFKC", full_name)

    # Step 2: trim
    text = text.strip()

    # Step 3: collapse whitespace
    text = " ".join(text.split())

    # Step 4: Turkish-aware lowercase
    # Python's str.lower() does NOT handle Turkish İ→i correctly (it gives 'i̇')
    # We must handle İ before lower() and ı→i explicitly
    text = text.replace("İ", "i").replace("I", "ı")  # Turkish I mapping
    text = text.lower()
    text = text.replace("ı", "i")  # Now ı→i after lowercasing

    # Step 5: transliterate Turkish chars
    text = text.translate(_TR_TRANS_TABLE)

    # Step 6: collapse any drift spaces
    text = " ".join(text.split())

    return text


# ---------------------------------------------------------------------------
# A.2  Phone normalization
# ---------------------------------------------------------------------------


class PhoneNormalizationResult:
    """Result of a phone normalization attempt."""

    __slots__ = ("phone_raw", "phone_e164", "status")

    def __init__(
        self,
        phone_raw: str | None,
        phone_e164: str | None,
        status: PhoneNormalizationStatus,
    ) -> None:
        self.phone_raw = phone_raw
        self.phone_e164 = phone_e164
        self.status = status


def normalize_phone(
    raw_input: str | None,
    *,
    default_region: str | None = None,
    allow_missing: bool = False,
) -> PhoneNormalizationResult:
    """Normalize a phone number to E.164 format (spec Appendix A.2).

    Args:
        raw_input: Original phone string from the caller.
        default_region: ISO 3166-1 alpha-2 region code. Defaults to settings.default_phone_region.
        allow_missing: If True, accept null/empty input (for import flows).

    Returns:
        PhoneNormalizationResult with phone_raw, phone_e164, and status.
    """
    region = default_region or settings.default_phone_region

    # Step 1: preserve original
    phone_raw = raw_input.strip() if raw_input else None

    # Step 2: null/empty
    if not phone_raw:
        if allow_missing:
            return PhoneNormalizationResult(
                phone_raw=None,
                phone_e164=None,
                status=PhoneNormalizationStatus.MISSING,
            )
        # For manual create, caller must handle MISSING as validation error
        return PhoneNormalizationResult(
            phone_raw=None,
            phone_e164=None,
            status=PhoneNormalizationStatus.MISSING,
        )

    # Steps 3-6: parse and normalize
    try:
        parsed = phonenumbers.parse(phone_raw, region)
    except phonenumbers.NumberParseException:
        return PhoneNormalizationResult(
            phone_raw=phone_raw,
            phone_e164=None,
            status=PhoneNormalizationStatus.RAW_UNKNOWN,
        )

    if not phonenumbers.is_valid_number(parsed):
        return PhoneNormalizationResult(
            phone_raw=phone_raw,
            phone_e164=None,
            status=PhoneNormalizationStatus.INVALID,
        )

    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return PhoneNormalizationResult(
        phone_raw=phone_raw,
        phone_e164=e164,
        status=PhoneNormalizationStatus.NORMALIZED,
    )


# ---------------------------------------------------------------------------
# Phone masking for MANAGER role (spec BR-17)
# ---------------------------------------------------------------------------


def mask_phone_for_manager(phone_e164: str | None) -> str | None:
    """Mask phone for MANAGER visibility: +90555*****67.

    Format: first 5 chars (country+area prefix) + masked middle + last 2 digits.
    """
    if not phone_e164:
        return None

    if len(phone_e164) < 8:
        return "*" * len(phone_e164)

    # Show first 5 chars and last 2 chars, mask the rest
    prefix = phone_e164[:5]
    suffix = phone_e164[-2:]
    masked_len = len(phone_e164) - 7
    return f"{prefix}{'*' * masked_len}{suffix}"


# ---------------------------------------------------------------------------
# ETag helpers (spec Section 12)
# ---------------------------------------------------------------------------


def etag_from_row_version(row_version: int) -> str:
    """Generate quoted ETag from row_version: '\"7\"'."""
    return f'"{row_version}"'


def parse_if_match(if_match: str | None) -> int | None:
    """Parse If-Match header value to row_version integer.

    Expected format: '"7"' (quoted integer).
    Returns None if header is missing or malformed.
    """
    if not if_match:
        return None
    stripped = if_match.strip().strip('"')
    try:
        return int(stripped)
    except ValueError:
        return None


def derive_lifecycle_state(status: str, soft_deleted_at_utc: object | None) -> str:
    """Return the externally visible lifecycle state for driver resources."""
    if soft_deleted_at_utc is not None:
        return "SOFT_DELETED"
    return str(status)
