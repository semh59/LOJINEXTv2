"""OCR field extraction from trip slip images using Tesseract.

Supports both legacy slip formats (DARA/BRÃœT/YÃœKLEME YERÄ°) and the
TARTIM FÄ°ÅÄ° format (TARTIM1/TARTIM2/PLAKA:/GELDÄ°ÄÄ° YER/GÄ°TTÄ°ÄÄ° YER).

Extraction priority for truck plate:
  1. Direct PLAKA: field (TARTIM FÄ°ÅÄ°)
  2. Generic plate regex scan (legacy slips)
"""

from __future__ import annotations

import io
import re

from PIL import Image

from telegram_service.schemas import SlipFields

# â”€â”€ Plate patterns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Turkish plate pattern: 34ABC1234 or 34AB1234 or 34A12345
_PLATE_RE = re.compile(r"\b([0-9]{2}\s?[A-ZÃ‡ÄÄ°Ã–ÅÃœ]{1,3}\s?[0-9]{2,5})\b", re.IGNORECASE)

# TARTIM FÄ°ÅÄ° (Weighing Slip): direct labeled PLAKA field (truck plate, priority)
_PLAKA_RE = re.compile(r"^PLAKA\s*:\s*([^\s\n]+)", re.IGNORECASE | re.MULTILINE)

# TARTIM FÄ°ÅÄ°: Trailer plate (DORSE PLAKA) embedded in AÃ‡IKLAMA line or standalone
_DORSE_RE = re.compile(r"DORSE\s*PLAKA\s*[:\s]+([^\s\n,]+)", re.IGNORECASE)

# â”€â”€ Date / time patterns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Generic date: DD.MM.YYYY or DD/MM/YYYY
_DATE_RE = re.compile(r"\b(\d{2})[./](\d{2})[./](\d{4})\b")

# Generic time: HH:MM
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")

# TARTIM FÄ°ÅÄ°: TARIH2 carries the weighing-out timestamp (priority for DATE2+TIME2)
_TARIH2_RE = re.compile(
    r"TARIH2\s*:\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})",
    re.IGNORECASE,
)

# â”€â”€ Slip number â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# TARTIM FÄ°ÅÄ°: Slip Number (NO) field at start of slip
_SLIP_NO_RE = re.compile(r"(?:^|\s)NO\s*:\s*(\d+)", re.IGNORECASE | re.MULTILINE)

# â”€â”€ Weight patterns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_WEIGHT_KW = {
    "tare": re.compile(
        r"(?:TARTIM1|DARA|TARE|BOÅ\s*AÄIRLIK|DARA\s*KG)[^\d]*(\d[\d\s,.]*)",
        re.IGNORECASE,
    ),
    "gross": re.compile(
        r"(?:TARTIM2|BRÃœT|GROSS|DOLU\s*AÄIRLIK|BRÃœT\s*KG)[^\d]*(\d[\d\s,.]*)",
        re.IGNORECASE,
    ),
    "net": re.compile(
        r"(?:NET|YÃœK\s*AÄIRLIK|NET\s*KG)[^\d]*(\d[\d\s,.]*)",
        re.IGNORECASE,
    ),
}

# â”€â”€ Origin / destination â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_ORIGIN_RE = re.compile(
    r"(?:GELDÄ°ÄÄ°\s*YER|YÃœKLEME\s*YERÄ°|Ã‡IKIÅ\s*YERÄ°|FROM|Ã‡IKIÅ|ORIGIN)[^\n:]*[:\s]+([^\n]+)",
    re.IGNORECASE,
)
_DEST_RE = re.compile(
    r"(?:GÄ°TTÄ°ÄÄ°\s*YER|TESLÄ°M\s*YERÄ°|VARIÅ\s*YERÄ°|TO|VARIÅ|DESTINATION)[^\n:]*[:\s]+([^\n]+)",
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
        raise RuntimeError("pytesseract is not installed. Install it with: pip install pytesseract") from exc

    image = Image.open(io.BytesIO(image_bytes))
    # Upscale small images to improve OCR accuracy
    if image.width < 1000:
        scale = 1000 / image.width
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)

    text = pytesseract.image_to_string(image, lang="tur+eng", config="--psm 6")

    fields = SlipFields(raw_text=text)

    # â”€â”€ Slip number (TARTIM FÄ°ÅÄ°: Weighing Slip NO field) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    slip_no_m = _SLIP_NO_RE.search(text)
    if slip_no_m:
        fields.slip_no = slip_no_m.group(1).strip()

    # â”€â”€ Truck plate: direct PLAKA: field first, then generic scan â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    plaka_m = _PLAKA_RE.search(text)
    if plaka_m:
        fields.truck_plate = plaka_m.group(1).replace(" ", "").upper()
    else:
        plates = [m.group(1).replace(" ", "").upper() for m in _PLATE_RE.finditer(text)]
        if plates:
            fields.truck_plate = plates[0]

    # â”€â”€ Trailer plate: DORSE PLAKA in AÃ‡IKLAMA, then second generic plate â”€â”€â”€â”€â”€
    dorse_m = _DORSE_RE.search(text)
    if dorse_m:
        fields.trailer_plate = dorse_m.group(1).replace(" ", "").upper()
    else:
        all_plates = [m.group(1).replace(" ", "").upper() for m in _PLATE_RE.finditer(text)]
        if len(all_plates) >= 2:
            fields.trailer_plate = all_plates[1]

    # â”€â”€ Date + time: TARIH2 first, then generic scan â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    tarih2_m = _TARIH2_RE.search(text)
    if tarih2_m:
        fields.trip_date = tarih2_m.group(1)
        fields.trip_time = tarih2_m.group(2)
    else:
        date_match = _DATE_RE.search(text)
        if date_match:
            fields.trip_date = f"{date_match.group(1)}.{date_match.group(2)}.{date_match.group(3)}"
        time_match = _TIME_RE.search(text)
        if time_match:
            fields.trip_time = f"{time_match.group(1)}:{time_match.group(2)}"

    # â”€â”€ Weights â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Origin / destination â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    origin_m = _ORIGIN_RE.search(text)
    if origin_m:
        fields.origin = origin_m.group(1).strip()

    dest_m = _DEST_RE.search(text)
    if dest_m:
        fields.destination = dest_m.group(1).strip()

    fields.ocr_confidence = fields.compute_confidence()
    return fields
