"""PDF statement generator — Driver Bonus Schedule (ŞOFÖR PRİM ÇİZELGESİ) template.

Layout: 8 trip cards per page (4 rows × 2 columns).
Card rows: NO, DATE (TARIH2), TIME (SAAT2), PLATE, ORIGIN, DESTINATION, NET, FEE, APPROVAL (ONAYI).
APPROVAL is left blank for manual signature.
"""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Table, TableStyle

from telegram_service.schemas import StatementRow

# ── Layout constants ──────────────────────────────────────────────────────────
_CARDS_PER_PAGE = 8
_CARD_ROWS_PER_PAGE = 4  # 4 rows × 2 columns

_PAGE_W, _PAGE_H = A4
_MARGIN = 10 * mm
_USABLE_W = _PAGE_W - 2 * _MARGIN  # ~190mm

_CARD_W = _USABLE_W / 2  # ~95mm per card
_LABEL_W = 36 * mm
_VALUE_W = _CARD_W - _LABEL_W  # ~59mm

_FONT_BOLD = "Helvetica-Bold"
_FONT_REGULAR = "Helvetica"
_FONT_SIZE = 8
_TITLE_FONT_SIZE = 10

_CARD_LABELS = [
    "NO",
    "TARIH2",
    "SAAT2",
    "PLAKA",
    "GELDİĞİ YER",
    "GİTTİĞİ YER",
    "NET",
    "ÜCRETİ",
    "ONAYI",
]
# ─────────────────────────────────────────────────────────────────────────────


def _card_values(row: StatementRow | None, seq_no: int) -> list[str]:
    """Return 9 value strings for the card fields."""
    if row is None:
        return [""] * len(_CARD_LABELS)
    no_val = row.slip_no if row.slip_no else str(seq_no)
    net_str = f"{row.net_weight_kg:,} kg".replace(",", ".")
    return [
        no_val,
        row.date,
        row.hour,
        row.truck_plate,
        row.origin,
        row.destination,
        net_str,
        row.fee,
        "",  # APPROVAL (ONAYI) — blank for manual signature
    ]


def _make_card(row: StatementRow | None, seq_no: int) -> Table:
    """Build one trip card as a ReportLab Table (label | value)."""
    values = _card_values(row, seq_no)
    data = [[label, val] for label, val in zip(_CARD_LABELS, values)]

    card = Table(data, colWidths=[_LABEL_W, _VALUE_W])
    card.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), _FONT_BOLD),
                ("FONTNAME", (1, 0), (1, -1), _FONT_REGULAR),
                ("FONTSIZE", (0, 0), (-1, -1), _FONT_SIZE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ]
        )
    )
    return card


def _make_card_pair(left: Table, right: Table) -> Table:
    """Place two cards side by side in a row."""
    pair = Table([[left, right]], colWidths=[_CARD_W, _CARD_W])
    pair.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return pair


def _make_page_header(driver_name: str, date_from: date) -> list:
    """Build title table and ADI SOYADI / AY/YIL info table."""
    month_year = date_from.strftime("%m/%Y")

    title_table = Table(
        [["ŞOFÖR PRİM ÇİZELGESİ"]],
        colWidths=[_USABLE_W],
    )
    title_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), _TITLE_FONT_SIZE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
            ]
        )
    )

    info_table = Table(
        [[f"ADI SOYADI: {driver_name}", f"AY/YIL: {month_year}"]],
        colWidths=[_USABLE_W / 2, _USABLE_W / 2],
    )
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), _FONT_SIZE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ]
        )
    )

    return [title_table, info_table]


def generate_statement_pdf(
    rows: list[StatementRow],
    driver_name: str,
    date_from: date,
    date_to: date,
) -> bytes:
    """Generate Driver Bonus Schedule (ŞOFÖR PRİM ÇİZELGESİ) PDF and return raw bytes.

    Args:
        rows: Trip rows mapped to StatementRow (from trip-service).
        driver_name: Full name of the driver (header ADI SOYADI).
        date_from: Start of date range (used for Month/Year header).
        date_to: End of date range (unused in layout, kept for API symmetry).

    Returns:
        Raw PDF bytes suitable for sending as a Telegram document.
    """
    del date_to
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"Driver Bonus Schedule — {driver_name}",
    )

    story: list = []

    # Always render at least one page even when rows is empty
    total_pages = max(1, -(-len(rows) // _CARDS_PER_PAGE))  # ceiling division

    for page_idx in range(total_pages):
        if page_idx > 0:
            story.append(PageBreak())

        story.extend(_make_page_header(driver_name, date_from))

        # Slice 8 rows for this page, pad with None for empty slots
        chunk_start = page_idx * _CARDS_PER_PAGE
        chunk = rows[chunk_start : chunk_start + _CARDS_PER_PAGE]
        padded: list[StatementRow | None] = list(chunk) + [None] * (_CARDS_PER_PAGE - len(chunk))

        for row_idx in range(_CARD_ROWS_PER_PAGE):
            left_item = padded[row_idx * 2]
            right_item = padded[row_idx * 2 + 1]

            left_seq = chunk_start + row_idx * 2 + 1
            right_seq = chunk_start + row_idx * 2 + 2

            left_card = _make_card(left_item, left_seq)
            right_card = _make_card(right_item, right_seq)
            story.append(_make_card_pair(left_card, right_card))

    doc.build(story)
    return buffer.getvalue()
