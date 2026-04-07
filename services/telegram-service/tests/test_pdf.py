"""Unit tests for PDF statement generation."""

from __future__ import annotations

from datetime import date

from telegram_service.pdf.generator import (
    _CARD_LABELS,
    _card_values,
    generate_statement_pdf,
)
from telegram_service.schemas import StatementRow


def _make_row(n: int, slip_no: str = "") -> StatementRow:
    return StatementRow(
        date=f"0{n}.03.2026",
        hour="08:00",
        truck_plate="34ABC1234",
        origin="İSTANBUL",
        destination="ANKARA",
        net_weight_kg=18000,
        fee="",
        approval="ONAYLANDI",
        slip_no=slip_no,
    )


class TestGenerateStatementPdf:
    def test_returns_bytes(self):
        rows = [_make_row(i) for i in range(1, 4)]
        pdf = generate_statement_pdf(
            rows=rows,
            driver_name="Ahmet Yılmaz",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
        )
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0

    def test_pdf_header_bytes(self):
        """PDF files start with the %PDF magic bytes."""
        rows = [_make_row(1)]
        pdf = generate_statement_pdf(
            rows=rows,
            driver_name="Test Driver",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
        )
        assert pdf[:4] == b"%PDF"

    def test_empty_rows_produces_valid_pdf(self):
        """Empty row list still produces a valid, non-empty PDF."""
        pdf = generate_statement_pdf(
            rows=[],
            driver_name="Ahmet Yılmaz",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
        )
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"

    def test_large_dataset(self):
        """100 rows should still produce a valid PDF (pagination)."""
        rows = [_make_row(i % 28 + 1) for i in range(100)]
        pdf = generate_statement_pdf(
            rows=rows,
            driver_name="Mehmet Kaya",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
        )
        assert pdf[:4] == b"%PDF"

    def test_turkish_characters(self):
        """Turkish special characters (İ, Ş, Ğ, etc.) don't crash PDF generation."""
        rows = [
            StatementRow(
                date="01.03.2026",
                hour="09:00",
                truck_plate="34ŞŞŞ1234",
                origin="İZMİR",
                destination="ŞANLIURFA",
                net_weight_kg=15000,
                fee="",
                approval="ONAYLANDI",
            )
        ]
        pdf = generate_statement_pdf(
            rows=rows,
            driver_name="Ömer Güneş",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
        )
        assert pdf[:4] == b"%PDF"


class TestCardTemplate:
    """Tests for the ŞOFÖR PRİM ÇİZELGESİ card layout internals."""

    def test_saat_row_not_in_card_labels(self):
        """SAATİ was removed from the template per design — must not appear."""
        assert "SAATİ" not in _CARD_LABELS

    def test_card_labels_count(self):
        assert len(_CARD_LABELS) == 9  # NO TARIH2 SAAT2 PLAKA GELDİĞİ GİTTİĞİ NET ÜCRETİ ONAYI

    def test_onayi_always_blank_regardless_of_row_approval(self):
        """ONAYI field in card is blank — manual signature; row.approval is not rendered."""
        row = _make_row(1)
        values = _card_values(row, seq_no=1)
        onayi_idx = _CARD_LABELS.index("ONAYI")
        assert values[onayi_idx] == ""

    def test_slip_no_used_as_no_field(self):
        row = _make_row(1, slip_no="40226")
        values = _card_values(row, seq_no=99)
        no_idx = _CARD_LABELS.index("NO")
        assert values[no_idx] == "40226"

    def test_seq_no_fallback_when_slip_no_empty(self):
        row = _make_row(1, slip_no="")
        values = _card_values(row, seq_no=5)
        no_idx = _CARD_LABELS.index("NO")
        assert values[no_idx] == "5"

    def test_none_row_produces_all_blank_values(self):
        values = _card_values(None, seq_no=1)
        assert all(v == "" for v in values)
        assert len(values) == len(_CARD_LABELS)

    def test_net_formatted_with_dot_separator(self):
        row = _make_row(1)
        values = _card_values(row, seq_no=1)
        net_idx = _CARD_LABELS.index("NET")
        assert "18.000" in values[net_idx]

    def test_9_rows_produces_two_page_pdf(self):
        """9 rows → 2 pages (8 on first, 1 real + 7 blank on second)."""
        rows = [_make_row(i % 9 + 1) for i in range(9)]
        pdf = generate_statement_pdf(
            rows=rows,
            driver_name="Test",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
        )
        assert pdf[:4] == b"%PDF"


class TestStatementRowMapping:
    def test_from_trip_service_row(self):
        raw = {
            "date": "2026-03-15",
            "hour": "08:30",
            "truck_plate": "34ABC1234",
            "from": "İSTANBUL",
            "to": "ANKARA",
            "net_weight_kg": 18000,
            "fee": "",
            "approval": "ONAYLANDI",
        }
        row = StatementRow.from_trip_service_row(raw)
        assert row.origin == "İSTANBUL"
        assert row.destination == "ANKARA"
        assert row.approval == "ONAYLANDI"  # passed through from trip-service

    def test_from_trip_service_row_missing_fields(self):
        raw = {"date": "2026-03-15", "net_weight_kg": 5000}
        row = StatementRow.from_trip_service_row(raw)
        assert row.origin == ""
        assert row.destination == ""
        assert row.truck_plate == ""

    def test_slip_no_from_source_slip_no(self):
        raw = {
            "date": "2026-03-15", "net_weight_kg": 5000,
            "source_slip_no": "40226", "trip_no": "TRP-0001",
        }
        row = StatementRow.from_trip_service_row(raw)
        assert row.slip_no == "40226"

    def test_slip_no_falls_back_to_trip_no(self):
        raw = {
            "date": "2026-03-15", "net_weight_kg": 5000,
            "source_slip_no": "", "trip_no": "TRP-0001",
        }
        row = StatementRow.from_trip_service_row(raw)
        assert row.slip_no == "TRP-0001"
