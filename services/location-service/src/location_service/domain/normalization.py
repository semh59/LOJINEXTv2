"""String normalization utilities (Section 5.1).

Provides Turkish and English normalization for location names.
"""

import re
import unicodedata


def _strip_and_collapse(text: str) -> str:
    """Remove punctuation and collapse multiple spaces into one."""
    # Remove punctuation (keep alphanumeric and whitespace)
    # \w matches unicode words, \s matches whitespace
    text = re.sub(r"[^\w\s]", "", text)
    # Collapse whitespace and trim
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_tr(text: str) -> str:
    """Normalize text according to Turkish locale rules.

    1. Handle Turkish dotted/dotless I/i
    2. Convert to uppercase
    3. Apply NFKC Unicode normalization
    4. Strip punctuation and collapse whitespace
    """
    if not text:
        return ""

    # Standard Python .upper() converts 'i' to 'I'. In Turkish, 'i' is 'İ'.
    # Similarly, standard .upper() on 'ı' might not be 'I' in some contexts.
    tr_text = text.replace("i", "İ").replace("ı", "I")
    tr_text = tr_text.upper()

    # NFKC normalizes composed characters
    nfkc_text = unicodedata.normalize("NFKC", tr_text)

    return _strip_and_collapse(nfkc_text)


def normalize_en(text: str) -> str:
    """Normalize text according to standard English (ROOT) rules.

    1. Convert to uppercase using standard ROOT behavior
    2. Apply NFKC Unicode normalization
    3. Strip punctuation and collapse whitespace
    """
    if not text:
        return ""

    nfkc_text = unicodedata.normalize("NFKC", text.upper())
    return _strip_and_collapse(nfkc_text)
