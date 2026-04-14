"""Handler flow tests using aiogram's test utilities."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

from telegram_service.handlers.statement import _parse_date
from telegram_service.schemas import SlipFields


class TestParseDateHelper:
    def test_dot_format(self):
        assert _parse_date("01.03.2026") == date(2026, 3, 1)

    def test_slash_format(self):
        assert _parse_date("01/03/2026") == date(2026, 3, 1)

    def test_invalid_format(self):
        assert _parse_date("2026-03-01") is None

    def test_invalid_date_value(self):
        assert _parse_date("32.13.2026") is None

    def test_whitespace_trimmed(self):
        assert _parse_date("  01.03.2026  ") == date(2026, 3, 1)


class TestSlipFieldsModel:
    def test_confidence_all_filled(self, full_slip_fields: SlipFields):
        assert full_slip_fields.ocr_confidence == 1.0

    def test_confidence_partial(self, partial_slip_fields: SlipFields):
        assert partial_slip_fields.ocr_confidence < 0.5

    def test_filled_count_full(self, full_slip_fields: SlipFields):
        assert full_slip_fields.filled_count() == 7

    def test_filled_count_partial(self, partial_slip_fields: SlipFields):
        assert partial_slip_fields.filled_count() < 7


class TestIsFullSlip:
    def test_returns_true_when_all_fields_present(self, full_slip_fields: SlipFields):
        from telegram_service.handlers.slip import _is_full_slip
        assert _is_full_slip(full_slip_fields) is True

    def test_returns_false_when_origin_missing(self, full_slip_fields: SlipFields):
        from telegram_service.handlers.slip import _is_full_slip
        full_slip_fields.origin = None
        assert _is_full_slip(full_slip_fields) is False

    def test_returns_false_when_weights_missing(self, full_slip_fields: SlipFields):
        from telegram_service.handlers.slip import _is_full_slip
        full_slip_fields.tare_kg = None
        assert _is_full_slip(full_slip_fields) is False


class TestTripClientToIso:
    def test_with_time(self):
        from telegram_service.clients.trip_client import _to_iso_local
        assert _to_iso_local("15.03.2026", "08:30") == "2026-03-15T08:30:00"

    def test_without_time_defaults_to_midnight(self):
        from telegram_service.clients.trip_client import _to_iso_local
        assert _to_iso_local("15.03.2026", None) == "2026-03-15T00:00:00"


class TestDriverClientCacheLogic:
    def test_cache_set_and_get(self):
        from telegram_service.auth import _cache_get, _cache_set
        _cache_set(12345, "DRV-AAA", "Test Name")
        result = _cache_get(12345)
        assert result == ("DRV-AAA", "Test Name")

    def test_cache_miss_returns_none(self):
        from telegram_service.auth import _cache_get
        assert _cache_get(99999) is None


class TestStatementDateValidation:
    async def test_date_range_exceeding_max_raises_message(self):
        """When date range exceeds max_date_range_days, user gets an error message."""
        from unittest.mock import MagicMock

        from aiogram.fsm.context import FSMContext

        message = MagicMock()
        message.text = "31.03.2026"
        message.answer = AsyncMock()

        state = AsyncMock(spec=FSMContext)
        state.get_data = AsyncMock(return_value={
            "date_from": "2026-01-01",
            "driver_id": "DRV123",
            "driver_name": "Test",
        })

        # date range = 89 days, exceeds 31
        with patch("telegram_service.config.settings") as mock_settings:
            mock_settings.max_date_range_days = 31

            from telegram_service.handlers.statement import handle_date_to
            await handle_date_to(message, state)

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert "31 gün" in call_text

    async def test_date_to_before_date_from_rejected(self):
        from unittest.mock import MagicMock

        from aiogram.fsm.context import FSMContext

        message = MagicMock()
        message.text = "01.01.2025"  # Before date_from
        message.answer = AsyncMock()

        state = AsyncMock(spec=FSMContext)
        state.get_data = AsyncMock(return_value={
            "date_from": "2026-03-01",
            "driver_id": "DRV123",
            "driver_name": "Test",
        })

        from telegram_service.handlers.statement import handle_date_to
        await handle_date_to(message, state)

        message.answer.assert_called_once()
        assert "önce olamaz" in message.answer.call_args[0][0]
