"""HTTP client for trip-service internal endpoints."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import httpx

from telegram_service.auth import issue_service_token
from telegram_service.config import settings
from telegram_service.schemas import SlipFields, StatementRow, TripIngestResult


async def _headers() -> dict[str, str]:
    token = await issue_service_token()
    return {
        "Authorization": f"Bearer {token}",
        "X-Correlation-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


async def ingest_slip(
    *,
    driver_id: str,
    vehicle_id: str,
    slip_no: str,
    reference_key: str,
    fields: SlipFields,
    timezone: str = "Europe/Istanbul",
) -> TripIngestResult:
    """Submit a fully parsed slip to trip-service ingest endpoint."""
    assert fields.tare_kg is not None
    assert fields.gross_kg is not None
    assert fields.net_kg is not None
    assert fields.origin is not None
    assert fields.destination is not None
    assert fields.trip_date is not None

    # Convert DD.MM.YYYY HH:MM → trip_start_local format (YYYY-MM-DDTHH:MM:00)
    trip_start_local = _to_iso_local(fields.trip_date, fields.trip_time)

    payload: dict[str, Any] = {
        "source_type": "TELEGRAM_TRIP_SLIP",
        "source_slip_no": slip_no,
        "source_reference_key": reference_key,
        "driver_id": driver_id,
        "vehicle_id": vehicle_id,
        "origin_name": fields.origin,
        "destination_name": fields.destination,
        "trip_start_local": trip_start_local,
        "trip_timezone": timezone,
        "tare_weight_kg": fields.tare_kg,
        "gross_weight_kg": fields.gross_kg,
        "net_weight_kg": fields.net_kg,
        "ocr_confidence": round(fields.ocr_confidence, 3),
        "normalized_truck_plate": fields.truck_plate,
        "normalized_trailer_plate": fields.trailer_plate,
    }

    async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
        resp = await client.post(
            f"{settings.trip_service_url}/internal/v1/trips/slips/ingest",
            json=payload,
            headers=await _headers(),
        )
        resp.raise_for_status()
        return TripIngestResult.model_validate(resp.json())


async def ingest_fallback(
    *,
    driver_id: str,
    reference_key: str,
    sent_at_utc: str,
    fallback_reason: str,
) -> TripIngestResult:
    """Submit a fallback (low-confidence / parse-failed) slip to trip-service."""
    payload: dict[str, Any] = {
        "source_reference_key": reference_key,
        "driver_id": driver_id,
        "message_sent_at_utc": sent_at_utc,
        "fallback_reason": fallback_reason,
    }

    async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
        resp = await client.post(
            f"{settings.trip_service_url}/internal/v1/trips/slips/ingest-fallback",
            json=payload,
            headers=await _headers(),
        )
        resp.raise_for_status()
        return TripIngestResult.model_validate(resp.json())


async def get_driver_statement(
    *,
    driver_id: str,
    date_from: date,
    date_to: date,
    timezone: str = "Europe/Istanbul",
) -> list[StatementRow]:
    """Fetch all completed trips for a driver in the given date range (auto-paginates)."""
    rows: list[StatementRow] = []
    page = 1

    async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
        headers = await _headers()
        while True:
            resp = await client.get(
                f"{settings.trip_service_url}/internal/v1/driver/trips",
                params={
                    "driver_id": driver_id,
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                    "timezone": timezone,
                    "page": page,
                    "per_page": 100,
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            items: list[dict[str, Any]] = data.get("items", [])
            rows.extend(StatementRow.from_trip_service_row(item) for item in items)

            meta = data.get("meta", {})
            if page >= meta.get("total_pages", 1):
                break
            page += 1

    return rows


def _to_iso_local(trip_date: str, trip_time: str | None) -> str:
    """Convert DD.MM.YYYY + optional HH:MM to YYYY-MM-DDTHH:MM:00."""
    day, month, year = trip_date.split(".")
    time_part = trip_time or "00:00"
    return f"{year}-{month}-{day}T{time_part}:00"
