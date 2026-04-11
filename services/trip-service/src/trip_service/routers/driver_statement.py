"""Driver statement endpoint for Telegram-facing exports."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trip_service.auth import AuthContext, telegram_service_auth_dependency
from trip_service.database import get_session
from trip_service.enums import TripStatus
from trip_service.errors import trip_date_range_too_large
from trip_service.middleware import date_range_to_utc, make_pagination_meta, parse_pagination
from trip_service.models import TripTrip
from trip_service.timezones import InvalidTimezoneError, utc_to_local
from trip_service.trip_helpers import latest_evidence

router = APIRouter(tags=["driver-statement"])


@router.get("/internal/v1/driver/trips")
async def driver_statement(
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(telegram_service_auth_dependency),
    driver_id: str = Query(..., min_length=1),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    timezone: str = Query("Europe/Istanbul"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    """Return completed non-empty-return trips for Telegram PDF generation."""
    _ = auth
    if date_from is not None and date_to is not None and (date_to - date_from).days > 30:
        raise trip_date_range_too_large("Driver statement range cannot exceed 31 days.")

    pagination = parse_pagination(page, per_page)
    stmt = (
        select(TripTrip)
        .options(selectinload(TripTrip.evidence))
        .where(
            TripTrip.driver_id == driver_id,
            TripTrip.status == TripStatus.COMPLETED,
            TripTrip.is_empty_return.is_(False),
        )
    )

    if date_from or date_to:
        utc_from, utc_to = date_range_to_utc(date_from, date_to, timezone)
        if utc_from:
            stmt = stmt.where(TripTrip.trip_datetime_utc >= utc_from)
        if utc_to:
            stmt = stmt.where(TripTrip.trip_datetime_utc < utc_to)

    total_items = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    trips = (
        (
            await session.execute(
                stmt.order_by(TripTrip.trip_datetime_utc.asc(), TripTrip.id.asc())
                .offset(pagination.offset)
                .limit(pagination.per_page)
            )
        )
        .scalars()
        .all()
    )

    rows: list[dict[str, Any]] = []
    for trip in trips:
        evidence = latest_evidence(trip)
        truck_plate = (evidence.normalized_truck_plate if evidence else None) or ""
        origin_name = (evidence.origin_name_raw if evidence else None) or trip.origin_name_snapshot or ""
        destination_name = (evidence.destination_name_raw if evidence else None) or trip.destination_name_snapshot or ""

        try:
            local_dt = utc_to_local(trip.trip_datetime_utc, trip.trip_timezone or timezone)
        except InvalidTimezoneError:
            local_dt = utc_to_local(trip.trip_datetime_utc, timezone)

        rows.append(
            {
                "date": local_dt.strftime("%Y-%m-%d"),
                "truck_plate": truck_plate,
                "from": origin_name,
                "to": destination_name,
                "net_weight_kg": trip.net_weight_kg or 0,
                "tare_weight_kg": trip.tare_weight_kg or 0,
                "gross_weight_kg": trip.gross_weight_kg or 0,
                "hour": local_dt.strftime("%H:%M"),
                "fee": "",
                "approval": "ONAYLANDI",
                "trip_no": trip.trip_no,
                "source_slip_no": trip.source_slip_no or "",
            }
        )

    return {
        "items": rows,
        "meta": make_pagination_meta(
            pagination.page,
            pagination.per_page,
            total_items,
            sort="trip_datetime_utc_asc,id_asc",
        ),
    }
