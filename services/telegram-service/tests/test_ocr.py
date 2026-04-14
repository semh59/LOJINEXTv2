"""Unit tests for OCR field extraction."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image

from telegram_service.ocr.extractor import (
    _DATE_RE,
    _DORSE_RE,
    _PLAKA_RE,
    _PLATE_RE,
    _SLIP_NO_RE,
    _TARIH2_RE,
    _TIME_RE,
    _parse_weight,
    extract_slip_fields,
)


class TestParseWeight:
    def test_plain_integer(self):
        assert _parse_weight("8000") == 8000

    def test_with_dots_as_thousands(self):
        assert _parse_weight("26.000") == 26000

    def test_with_spaces(self):
        assert _parse_weight("8 000") == 8000

    def test_invalid_returns_none(self):
        assert _parse_weight("abc") is None

    def test_with_trailing_whitespace(self):
        assert _parse_weight("  8000  ") == 8000


class TestPlateRegex:
    def test_standard_plate(self):
        matches = list(_PLATE_RE.finditer("Araç: 34ABC1234"))
        assert len(matches) == 1
        assert matches[0].group(1).replace(" ", "") == "34ABC1234"

    def test_two_plate_format(self):
        text = "Araç: 34ABC1234  Dorse: 06XY5678"
        matches = [m.group(1).replace(" ", "") for m in _PLATE_RE.finditer(text)]
        assert len(matches) == 2
        assert matches[0] == "34ABC1234"
        assert matches[1] == "06XY5678"

    def test_no_plate(self):
        assert list(_PLATE_RE.finditer("Tarih: 15.03.2026")) == []


class TestDateRegex:
    def test_dot_separator(self):
        m = _DATE_RE.search("Tarih: 15.03.2026")
        assert m is not None
        assert m.group(1) == "15"
        assert m.group(2) == "03"
        assert m.group(3) == "2026"

    def test_slash_separator(self):
        m = _DATE_RE.search("Date: 15/03/2026")
        assert m is not None

    def test_no_date(self):
        assert _DATE_RE.search("No date here") is None


class TestTimeRegex:
    def test_standard_time(self):
        m = _TIME_RE.search("Saat: 08:30")
        assert m is not None
        assert m.group(1) == "08"
        assert m.group(2) == "30"

    def test_midnight(self):
        m = _TIME_RE.search("00:00")
        assert m is not None

    def test_no_time(self):
        assert _TIME_RE.search("tarih 15.03.2026") is None


class TestExtractSlipFields:
    def _make_image_bytes(self) -> bytes:
        """Create a minimal PNG image in memory."""
        img = Image.new("RGB", (100, 100), color="white")
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_full_slip_extraction(self):
        """OCR returns text with all fields — all are extracted."""
        ocr_text = (
            "YÜKLEME YERİ: İSTANBUL\n"
            "TESLİM YERİ: ANKARA\n"
            "Araç Plakası: 34ABC1234\n"
            "Dorse Plakası: 06XY5678\n"
            "Tarih: 15.03.2026  Saat: 08:30\n"
            "DARA: 8000\n"
            "BRÜT: 26000\n"
            "NET: 18000\n"
        )
        with patch("pytesseract.image_to_string", return_value=ocr_text):
            fields = extract_slip_fields(self._make_image_bytes())

        assert fields.truck_plate == "34ABC1234"
        assert fields.trailer_plate == "06XY5678"
        assert fields.origin == "İSTANBUL"
        assert fields.destination == "ANKARA"
        assert fields.trip_date == "15.03.2026"
        assert fields.trip_time == "08:30"
        assert fields.tare_kg == 8000
        assert fields.gross_kg == 26000
        assert fields.net_kg == 18000
        assert fields.ocr_confidence == 1.0

    def test_partial_slip_low_confidence(self):
        """Only plate and date extracted — confidence is low."""
        ocr_text = "34ABC1234\n15.03.2026\n"
        with patch("pytesseract.image_to_string", return_value=ocr_text):
            fields = extract_slip_fields(self._make_image_bytes())

        assert fields.truck_plate == "34ABC1234"
        assert fields.trip_date == "15.03.2026"
        assert fields.origin is None
        assert fields.tare_kg is None
        assert fields.ocr_confidence < 0.5

    def test_net_weight_inferred(self):
        """Net weight is inferred from tare + gross when not explicitly present."""
        ocr_text = (
            "YÜKLEME YERİ: İZMİR\n"
            "TESLİM YERİ: BURSA\n"
            "34ABC1234  15.03.2026\n"
            "DARA: 8000\n"
            "BRÜT: 26000\n"
        )
        with patch("pytesseract.image_to_string", return_value=ocr_text):
            fields = extract_slip_fields(self._make_image_bytes())

        assert fields.net_kg == 18000

    def test_pytesseract_not_installed(self, monkeypatch):
        """Raises RuntimeError when pytesseract is not importable."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pytesseract":
                raise ImportError("No module named 'pytesseract'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(RuntimeError, match="pytesseract is not installed"):
            extract_slip_fields(self._make_image_bytes())


class TestTartimFisiRegexes:
    """Unit tests for TARTIM FİŞİ-specific regex patterns."""

    def test_plaka_direct_field(self):
        m = _PLAKA_RE.search("PLAKA:     27UN195")
        assert m is not None
        assert m.group(1) == "27UN195"

    def test_plaka_with_spaces_around_colon(self):
        m = _PLAKA_RE.search("PLAKA :  06ABC123")
        assert m is not None
        assert m.group(1) == "06ABC123"

    def test_plaka_not_matched_mid_line(self):
        """PLAKA: only matches at start of line (multiline anchor)."""
        m = _PLAKA_RE.search("MUSTERI: PLAKA: 27UN195")
        assert m is None

    def test_tarih2_date_and_time(self):
        m = _TARIH2_RE.search("TARIH2:    18.03.2026 15:56:42")
        assert m is not None
        assert m.group(1) == "18.03.2026"
        assert m.group(2) == "15:56"

    def test_tarih2_no_match_for_tarih1(self):
        m = _TARIH2_RE.search("TARIH1:    17.03.2026 17:32:48")
        assert m is None

    def test_slip_no_extraction(self):
        m = _SLIP_NO_RE.search("NO:        40226")
        assert m is not None
        assert m.group(1) == "40226"

    def test_dorse_re_from_aciklama(self):
        m = _DORSE_RE.search("AÇIKLAMA:  DORSE PLAKA:27ATF028")
        assert m is not None
        assert m.group(1) == "27ATF028"

    def test_dorse_re_with_space(self):
        m = _DORSE_RE.search("DORSE PLAKA: 06XY5678")
        assert m is not None
        assert m.group(1) == "06XY5678"


class TestTartimFisiFullExtraction:
    """Integration tests for TARTIM FİŞİ OCR extraction via extract_slip_fields."""

    def _make_image_bytes(self) -> bytes:
        img = Image.new("RGB", (100, 100), color="white")
        import io as _io
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_tartim_fisi_full_extraction(self):
        """All TARTIM FİŞİ fields are correctly extracted."""
        ocr_text = (
            "NO:        40226           TARIH2:    18.03.2026 15:56\n"
            "PLAKA:     27UN195         TARIH1:    17.03.2026 17:32\n"
            "MUSTERI:   MUTLU UN\n"
            "GELDİĞİ YER:  MUTLU UN TEKİRDAĞ\n"
            "GİTTİĞİ YER:  CEYPORT LİMANI\n"
            "AÇIKLAMA:  DORSE PLAKA:27ATF028\n"
            "TARTIM2:   050220 kg\n"
            "TARTIM1:   015120 kg\n"
            "NET:       35100 kg\n"
        )
        with patch("pytesseract.image_to_string", return_value=ocr_text):
            fields = extract_slip_fields(self._make_image_bytes())

        assert fields.slip_no == "40226"
        assert fields.truck_plate == "27UN195"
        assert fields.trailer_plate == "27ATF028"
        assert fields.trip_date == "18.03.2026"
        assert fields.trip_time == "15:56"
        assert fields.origin == "MUTLU UN TEKİRDAĞ"
        assert fields.destination == "CEYPORT LİMANI"
        assert fields.gross_kg == 50220
        assert fields.tare_kg == 15120
        assert fields.net_kg == 35100

    def test_tartim1_tartim2_weight_parsing(self):
        """TARTIM1 maps to tare, TARTIM2 maps to gross."""
        ocr_text = (
            "PLAKA: 34ABC1234\n"
            "GELDİĞİ YER: A\n"
            "GİTTİĞİ YER: B\n"
            "TARTIM2: 26000 kg\n"
            "TARTIM1: 8000 kg\n"
            "NET: 18000 kg\n"
        )
        with patch("pytesseract.image_to_string", return_value=ocr_text):
            fields = extract_slip_fields(self._make_image_bytes())

        assert fields.tare_kg == 8000
        assert fields.gross_kg == 26000
        assert fields.net_kg == 18000

    def test_plaka_direct_field_wins_over_generic_scan(self):
        """When PLAKA: field is present, it takes priority over generic regex."""
        ocr_text = (
            "PLAKA:     27UN195\n"
            "Araç: 34ABC1234\n"  # generic plate in text — must NOT become truck_plate
            "GELDİĞİ YER: A\n"
            "GİTTİĞİ YER: B\n"
            "TARTIM2: 26000\nTARTIM1: 8000\nNET: 18000\n"
        )
        with patch("pytesseract.image_to_string", return_value=ocr_text):
            fields = extract_slip_fields(self._make_image_bytes())

        assert fields.truck_plate == "27UN195"

    def test_tarih2_date_time_priority(self):
        """TARIH2 timestamp wins over generic date scan (TARIH1 is ignored)."""
        ocr_text = (
            "NO: 1\nPLAKA: 34ABC1234\n"
            "TARIH2: 18.03.2026 15:56\n"
            "TARIH1: 17.03.2026 09:00\n"
            "GELDİĞİ YER: A\nGİTTİĞİ YER: B\n"
            "TARTIM2: 26000\nTARTIM1: 8000\nNET: 18000\n"
        )
        with patch("pytesseract.image_to_string", return_value=ocr_text):
            fields = extract_slip_fields(self._make_image_bytes())

        assert fields.trip_date == "18.03.2026"
        assert fields.trip_time == "15:56"

    def test_dorse_plaka_from_aciklama_line(self):
        """Trailer plate is extracted from AÇIKLAMA: DORSE PLAKA: line."""
        ocr_text = (
            "PLAKA: 27UN195\n"
            "GELDİĞİ YER: A\nGİTTİĞİ YER: B\n"
            "AÇIKLAMA: DORSE PLAKA:27ATF028\n"
            "TARTIM2: 26000\nTARTIM1: 8000\nNET: 18000\n"
        )
        with patch("pytesseract.image_to_string", return_value=ocr_text):
            fields = extract_slip_fields(self._make_image_bytes())

        assert fields.trailer_plate == "27ATF028"
