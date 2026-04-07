"""HTTP client tests using respx to mock httpx calls."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from telegram_service.schemas import SlipFields


@pytest.fixture(autouse=True)
def mock_service_token():
    """Mock service token issuance for all client tests.

    Patch at the usage site (where the name is bound after 'from X import Y'),
    not at the definition site.
    """
    with (
        patch(
            "telegram_service.clients.trip_client.issue_service_token",
            new=AsyncMock(return_value="mock-service-token"),
        ),
        patch(
            "telegram_service.clients.driver_client.issue_service_token",
            new=AsyncMock(return_value="mock-service-token"),
        ),
    ):
        yield


class TestTripClient:
    @respx.mock
    async def test_ingest_slip_success(self):
        from telegram_service.clients.trip_client import ingest_slip

        respx.post("http://localhost:8101/internal/v1/trips/slips/ingest").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "01ABC123456789012345678901",
                    "trip_no": "TRP-0001",
                    "status": "PENDING_REVIEW",
                    "source_type": "TELEGRAM_TRIP_SLIP",
                },
            )
        )

        fields = SlipFields(
            truck_plate="34ABC1234",
            origin="İSTANBUL",
            destination="ANKARA",
            trip_date="15.03.2026",
            trip_time="08:30",
            tare_kg=8000,
            gross_kg=26000,
            net_kg=18000,
            ocr_confidence=1.0,
        )
        result = await ingest_slip(
            driver_id="DRV123",
            vehicle_id="34ABC1234",
            slip_no="msg-1",
            reference_key="tg:msg-1",
            fields=fields,
        )

        assert result.trip_no == "TRP-0001"
        assert result.status == "PENDING_REVIEW"

    @respx.mock
    async def test_ingest_fallback_success(self):
        from telegram_service.clients.trip_client import ingest_fallback

        respx.post("http://localhost:8101/internal/v1/trips/slips/ingest-fallback").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "01ABC123456789012345678902",
                    "trip_no": "TRP-0002",
                    "status": "PENDING_REVIEW",
                    "source_type": "TELEGRAM_TRIP_SLIP",
                },
            )
        )

        result = await ingest_fallback(
            driver_id="DRV123",
            reference_key="tg:msg-2",
            sent_at_utc=datetime.now(tz=timezone.utc).isoformat(),
            fallback_reason="OCR confidence below threshold",
        )

        assert result.trip_no == "TRP-0002"

    @respx.mock
    async def test_get_driver_statement_single_page(self):
        from telegram_service.clients.trip_client import get_driver_statement

        respx.get("http://localhost:8101/internal/v1/driver/trips").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "date": "2026-03-15",
                            "hour": "08:30",
                            "truck_plate": "34ABC1234",
                            "from": "İSTANBUL",
                            "to": "ANKARA",
                            "net_weight_kg": 18000,
                            "fee": "",
                            "approval": "ONAYLANDI",
                            "source_slip_no": "",
                            "trip_no": "TRP-0001",
                        }
                    ],
                    "meta": {"page": 1, "per_page": 100, "total_items": 1, "total_pages": 1, "sort": ""},
                },
            )
        )

        rows = await get_driver_statement(
            driver_id="DRV123",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
        )

        assert len(rows) == 1
        assert rows[0].origin == "İSTANBUL"
        assert rows[0].approval == "ONAYLANDI"

    @respx.mock
    async def test_get_driver_statement_multi_page(self):
        from telegram_service.clients.trip_client import get_driver_statement

        def _row(n: int) -> dict:
            return {
                "date": f"2026-03-{n:02d}",
                "hour": "09:00",
                "truck_plate": "34ABC1234",
                "from": "A",
                "to": "B",
                "net_weight_kg": 10000,
                "fee": "",
                "approval": "",
            }

        call_count = 0

        def side_effect(req):
            nonlocal call_count
            call_count += 1
            page = int(req.url.params.get("page", "1"))
            if page == 1:
                return httpx.Response(200, json={
                    "items": [_row(i) for i in range(1, 6)],
                    "meta": {"page": 1, "per_page": 100, "total_items": 10, "total_pages": 2, "sort": ""},
                })
            return httpx.Response(200, json={
                "items": [_row(i) for i in range(6, 11)],
                "meta": {"page": 2, "per_page": 100, "total_items": 10, "total_pages": 2, "sort": ""},
            })

        respx.get("http://localhost:8101/internal/v1/driver/trips").mock(side_effect=side_effect)

        rows = await get_driver_statement(
            driver_id="DRV123",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
        )

        assert len(rows) == 10
        assert call_count == 2

    @respx.mock
    async def test_ingest_slip_raises_on_4xx(self):
        from telegram_service.clients.trip_client import ingest_slip

        respx.post("http://localhost:8101/internal/v1/trips/slips/ingest").mock(
            return_value=httpx.Response(422, json={"detail": "validation error"})
        )

        fields = SlipFields(
            truck_plate="34ABC1234",
            origin="A",
            destination="B",
            trip_date="15.03.2026",
            tare_kg=8000,
            gross_kg=26000,
            net_kg=18000,
            ocr_confidence=1.0,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await ingest_slip(
                driver_id="DRV123",
                vehicle_id="34ABC1234",
                slip_no="msg-1",
                reference_key="tg:msg-1",
                fields=fields,
            )


class TestDriverClient:
    @respx.mock
    async def test_lookup_found(self):
        from telegram_service.clients.driver_client import lookup_by_telegram_id

        respx.get("http://localhost:8104/internal/v1/drivers/lookup").mock(
            return_value=httpx.Response(
                200,
                json={
                    "driver_id": "DRV123456789012345678901234",
                    "full_name": "Ahmet Yılmaz",
                    "telegram_user_id": "123456789",
                    "status": "ACTIVE",
                    "is_assignable": True,
                },
            )
        )

        result = await lookup_by_telegram_id(123456789)

        assert result is not None
        assert result.driver_id == "DRV123456789012345678901234"
        assert result.full_name == "Ahmet Yılmaz"

    @respx.mock
    async def test_lookup_not_found(self):
        from telegram_service.clients.driver_client import lookup_by_telegram_id

        respx.get("http://localhost:8104/internal/v1/drivers/lookup").mock(
            return_value=httpx.Response(404)
        )

        result = await lookup_by_telegram_id(999999999)
        assert result is None

    @respx.mock
    async def test_lookup_uses_cache_on_second_call(self):
        from telegram_service.clients.driver_client import lookup_by_telegram_id

        call_count = 0

        def side_effect(_request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={
                "driver_id": "DRV123",
                "full_name": "Test Driver",
                "telegram_user_id": "111",
                "status": "ACTIVE",
                "is_assignable": True,
            })

        respx.get("http://localhost:8104/internal/v1/drivers/lookup").mock(side_effect=side_effect)

        await lookup_by_telegram_id(111)
        await lookup_by_telegram_id(111)

        assert call_count == 1  # Cache hit on second call
