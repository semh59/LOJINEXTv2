"""OCR field extraction from trip slip images using Tesseract.

Supports both legacy slip formats (DARA/BRÜT/YÜKLEME YERİ) and the
TARTIM FİŞİ format (TARTIM1/TARTIM2/PLAKA:/GELDİĞİ YER/GİTTİĞİ YER).

Extraction priority for truck plate:
  1. Direct PLAKA: field (TARTIM FİŞİ)
  2. Generic plate regex scan (legacy slips)
"""

from __future__ import annotations

import io
import re

from PIL import Image

from telegram_service.schemas import SlipFields

# ── Plate patterns ────────────────────────────────────────────────────────────

# Turkish plate pattern: 34ABC1234 or 34AB1234 or 34A12345
_PLATE_RE = re.compile(r"\b([0-9]{2}\s?[A-ZÇĞİÖŞÜ]{1,3}\s?[0-9]{2,5})\b", re.IGNORECASE)

# TARTIM FİŞİ: direct labeled PLAKA field (truck plate, priority)
_PLAKA_RE = re.compile(r"^PLAKA\s*:\s*([^\s\n]+)", re.IGNORECASE | re.MULTILINE)

# TARTIM FİŞİ: DORSE PLAKA embedded in AÇIKLAMA line or standalone
_DORSE_RE = re.compile(r"DORSE\s*PLAKA\s*[:\s]+([^\s\n,]+)", re.IGNORECASE)

# ── Date / time patterns ──────────────────────────────────────────────────────

# Generic date: DD.MM.YYYY or DD/MM/YYYY
_DATE_RE = re.compile(r"\b(\d{2})[./](\d{2})[./](\d{4})\b")

# Generic time: HH:MM
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")

# TARTIM FİŞİ: TARIH2 carries the weighing-out timestamp (priority for date+time)
_TARIH2_RE = re.compile(
    r"TARIH2\s*:\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})",
    re.IGNORECASE,
)

# ── Slip number ───────────────────────────────────────────────────────────────

# TARTIM FİŞİ: NO field at start of slip
_SLIP_NO_RE = re.compile(r"(?:^|\s)NO\s*:\s*(\d+)", re.IGNORECASE | re.MULTILINE)

# ── Weight patterns ───────────────────────────────────────────────────────────

_WEIGHT_KW = {
    "tare": re.compile(
        r"(?:TARTIM1|DARA|TARE|BOŞ\s*AĞIRLIK|DARA\s*KG)[^\d]*(\d[\d\s,.]*)",
        re.IGNORECASE,
    ),
    "gross": re.compile(
        r"(?:TARTIM2|BRÜT|GROSS|DOLU\s*AĞIRLIK|BRÜT\s*KG)[^\d]*(\d[\d\s,.]*)",
        re.IGNORECASE,
    ),
    "net": re.compile(
        r"(?:NET|YÜK\s*AĞIRLIK|NET\s*KG)[^\d]*(\d[\d\s,.]*)",
        re.IGNORECASE,
    ),
}

# ── Origin / destination ──────────────────────────────────────────────────────

_ORIGIN_RE = re.compile(
    r"(?:GELDİĞİ\s*YER|YÜKLEME\s*YERİ|ÇIKIŞ\s*YERİ|FROM|ÇIKIŞ|ORIGIN)[^\n:]*[:\s]+([^\n]+)",
    re.IGNORECASE,
)
_DEST_RE = re.compile(
    r"(?:GİTTİĞİ\s*YER|TESLİM\s*YERİ|VARIŞ\s*YERİ|TO|VARIŞ|DESTINATION)[^\n:]*[:\s]+([^\n]+)",
    re.IGNORECASE,
)


def _parse_weight(raw: str) -> int | None:
    """Parse a weight string to integer kg, stripping separators."""
    cleaned = re.sub(r"[\s,.]", "", raw.strip())
    try:
        return int(cleaned)
    except ValueError:
        return None


def extract_slip_fields(image_bytes: bytes) -> SlipFields:
    """Run Tesseract OCR on image bytes and extract slip fields.

    Returns SlipFields with extracted values and a computed confidence score.
    Requires Tesseract with Turkish language pack installed on the system.
    """
    try:
        import pytesseract  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pytesseract is not installed. Install it with: pip install pytesseract"
        ) from exc

    image = Image.open(io.BytesIO(image_bytes))
    # Upscale small images to improve OCR accuracy
    if image.width < 1000:
        scale = 1000 / image.width
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)), Image.LANCZOS
        )

    text = pytesseract.image_to_string(image, lang="tur+eng", config="--psm 6")

    fields = SlipFields(raw_text=text)

    # ── Slip number (TARTIM FİŞİ: NO field) ──────────────────────────────────
    slip_no_m = _SLIP_NO_RE.search(text)
    if slip_no_m:
        fields.slip_no = slip_no_m.group(1).strip()

    # ── Truck plate: direct PLAKA: field first, then generic scan ─────────────
    plaka_m = _PLAKA_RE.search(text)
    if plaka_m:
        fields.truck_plate = plaka_m.group(1).replace(" ", "").upper()
    else:
        plates = [m.group(1).replace(" ", "").upper() for m in _PLATE_RE.finditer(text)]
        if plates:
            fields.truck_plate = plates[0]

    # ── Trailer plate: DORSE PLAKA in AÇIKLAMA, then second generic plate ─────
    dorse_m = _DORSE_RE.search(text)
    if dorse_m:
        fields.trailer_plate = dorse_m.group(1).replace(" ", "").upper()
    else:
        all_plates = [m.group(1).replace(" ", "").upper() for m in _PLATE_RE.finditer(text)]
        if len(all_plates) >= 2:
            fields.trailer_plate = all_plates[1]

    # ── Date + time: TARIH2 first, then generic scan ──────────────────────────
    tarih2_m = _TARIH2_RE.search(text)
    if tarih2_m:
        fields.trip_date = tarih2_m.group(1)
        fields.trip_time = tarih2_m.group(2)
    else:
        date_match = _DATE_RE.search(text)
        if date_match:
            fields.trip_date = (
                f"{date_match.group(1)}.{date_match.group(2)}.{date_match.group(3)}"
            )
        time_match = _TIME_RE.search(text)
        if time_match:
            fields.trip_time = f"{time_match.group(1)}:{time_match.group(2)}"

    # ── Weights ───────────────────────────────────────────────────────────────
    for key, pattern in _WEIGHT_KW.items():
        m = pattern.search(text)
        if m:
            parsed = _parse_weight(m.group(1))
            if key == "tare":
                fields.tare_kg = parsed
            elif key == "gross":
                fields.gross_kg = parsed
            elif key == "net":
                fields.net_kg = parsed

    # Infer net if tare + gross present but net missing
    if fields.tare_kg is not None and fields.gross_kg is not None and fields.net_kg is None:
        fields.net_kg = fields.gross_kg - fields.tare_kg

    # ── Origin / destination ──────────────────────────────────────────────────
    origin_m = _ORIGIN_RE.search(text)
    if origin_m:
        fields.origin = origin_m.group(1).strip()

    dest_m = _DEST_RE.search(text)
    if dest_m:
        fields.destination = dest_m.group(1).strip()

    fields.ocr_confidence = fields.compute_confidence()
    return fields
