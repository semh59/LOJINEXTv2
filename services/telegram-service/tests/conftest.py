"""Shared test fixtures for telegram-service."""

from __future__ import annotations

import pytest

from telegram_service.auth import cache_clear
from telegram_service.schemas import SlipFields


@pytest.fixture(autouse=True)
def clear_driver_cache():
    """Ensure the driver identity cache is clean between tests."""
    cache_clear()
    yield
    cache_clear()


@pytest.fixture()
def full_slip_fields() -> SlipFields:
    """A fully populated SlipFields with high confidence."""
    fields = SlipFields(
        truck_plate="34ABC1234",
        trailer_plate="06XY5678",
        origin="İSTANBUL",
        destination="ANKARA",
        trip_date="15.03.2026",
        trip_time="08:30",
        tare_kg=8000,
        gross_kg=26000,
        net_kg=18000,
        raw_text="sample ocr text",
    )
    fields.ocr_confidence = fields.compute_confidence()
    return fields


@pytest.fixture()
def partial_slip_fields() -> SlipFields:
    """A partially populated SlipFields with low confidence."""
    fields = SlipFields(
        truck_plate="34ABC1234",
        origin=None,
        destination=None,
        trip_date="15.03.2026",
        tare_kg=None,
        gross_kg=None,
        net_kg=None,
        raw_text="partial ocr text",
    )
    fields.ocr_confidence = fields.compute_confidence()
    return fields
