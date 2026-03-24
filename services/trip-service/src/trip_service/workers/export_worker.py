"""Export worker — V8 Section 17.

Generates .xlsx export files with 20 columns.

V8 Section 17.2 — Export columns include origin/destination which use
the Location Service fallback chain (Section 11.2):
  1. Location Service display name by route_id
  2. Evidence origin_name_raw / destination_name_raw
  3. Empty string
"""

from __future__ import annotations

import json
import logging
from datetime import date as date_type
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ulid import ULID

from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.enums import ExportJobStatus, TripStatus
from trip_service.middleware import date_range_to_utc
from trip_service.models import TripExportJob, TripTrip

logger = logging.getLogger("trip_service.export_worker")


def _generate_id() -> str:
    return str(ULID())


def _now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


async def process_export_job(job_id: str) -> None:
    """Process a single export job — query trips, generate .xlsx."""
    async with async_session_factory() as session:
        result = await session.execute(select(TripExportJob).where(TripExportJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("Export job %s not found", job_id)
            return

        if job.status != ExportJobStatus.PENDING:
            logger.warning("Export job %s is not PENDING", job_id)
            return

        # Mark RUNNING
        job.status = ExportJobStatus.RUNNING
        job.updated_at_utc = _now_utc()
        await session.commit()

    try:
        # Parse filters
        filters = (
            json.loads(job.requested_filters_json)
            if isinstance(job.requested_filters_json, str)
            else job.requested_filters_json
        )
        filter_data = filters.get("filters", filters)

        async with async_session_factory() as session:
            # Build query
            stmt = select(TripTrip).options(selectinload(TripTrip.evidence), selectinload(TripTrip.enrichment))

            # Default: exclude soft-deleted
            if not filter_data.get("include_soft_deleted", False):
                stmt = stmt.where(TripTrip.status != TripStatus.SOFT_DELETED)

            if filter_data.get("driver_id"):
                stmt = stmt.where(TripTrip.driver_id == filter_data["driver_id"])
            if filter_data.get("vehicle_id"):
                stmt = stmt.where(TripTrip.vehicle_id == filter_data["vehicle_id"])
            if filter_data.get("route_id"):
                stmt = stmt.where(TripTrip.route_id == filter_data["route_id"])

            # Date filter
            date_from = filter_data.get("date_from")
            date_to = filter_data.get("date_to")
            timezone = filter_data.get("timezone", "Europe/Istanbul")
            if date_from or date_to:
                df = date_type.fromisoformat(date_from) if date_from else None
                dt = date_type.fromisoformat(date_to) if date_to else None
                utc_from, utc_to = date_range_to_utc(df, dt, timezone)
                if utc_from:
                    stmt = stmt.where(TripTrip.trip_datetime_utc >= utc_from)
                if utc_to:
                    stmt = stmt.where(TripTrip.trip_datetime_utc < utc_to)

            stmt = stmt.order_by(TripTrip.trip_datetime_utc.desc(), TripTrip.id.desc())
            results = await session.execute(stmt)
            trips = results.scalars().all()

        # Generate .xlsx with 20 columns (V8 Section 17.2)
        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is None:
            ws = wb.create_sheet()

        # V8 Section 17.2 — 20 export columns
        headers = [
            "trip_id",
            "trip_no",
            "source_type",
            "driver_id",
            "vehicle_id",
            "trailer_id",
            "route_id",
            "origin",
            "destination",  # Fallback chain: Location → evidence → ""
            "trip_datetime_utc",
            "trip_timezone",
            "tare_weight_kg",
            "gross_weight_kg",
            "net_weight_kg",
            "is_empty_return",
            "status",
            "enrichment_status",
            "route_status",
            "weather_status",
            "created_at_utc",
        ]
        ws.append(headers)

        for trip in trips:
            # V8 Section 11.2 — Fallback chain for origin/destination
            # 1. Location Service display name by route_id (TODO: call service)
            # 2. Evidence origin/destination_name_raw
            # 3. Empty string
            evidence = trip.evidence[-1] if trip.evidence else None
            origin = (evidence.origin_name_raw if evidence else None) or ""
            destination = (evidence.destination_name_raw if evidence else None) or ""

            enrichment_status = trip.enrichment.enrichment_status if trip.enrichment else ""
            route_status = trip.enrichment.route_status if trip.enrichment else ""
            weather_status = trip.enrichment.weather_status if trip.enrichment else ""

            ws.append(
                [
                    trip.id,
                    trip.trip_no,
                    trip.source_type,
                    trip.driver_id,
                    trip.vehicle_id or "",
                    trip.trailer_id or "",
                    trip.route_id or "",
                    origin,
                    destination,
                    str(trip.trip_datetime_utc),
                    trip.trip_timezone,
                    trip.tare_weight_kg,
                    trip.gross_weight_kg,
                    trip.net_weight_kg,
                    str(trip.is_empty_return),
                    trip.status,
                    enrichment_status,
                    route_status,
                    weather_status,
                    str(trip.created_at_utc),
                ]
            )

        # Save file
        file_key = f"exports/{job_id}/{_generate_id()}.xlsx"
        storage_path = Path(settings.storage_local_path)
        full_path = storage_path / file_key
        full_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(full_path))
        wb.close()

        # Update job
        now = _now_utc()
        async with async_session_factory() as session:
            result = await session.execute(select(TripExportJob).where(TripExportJob.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                job.status = ExportJobStatus.COMPLETED
                job.result_file_key = file_key
                job.result_file_expires_at_utc = now + timedelta(hours=settings.export_presigned_url_ttl_hours)
                job.completed_at_utc = now
                job.updated_at_utc = now
                await session.commit()

        logger.info("Export job %s: COMPLETED — %d trips exported", job_id, len(trips))

    except Exception as e:
        logger.error("Export job %s: FAILED — %s", job_id, e)
        async with async_session_factory() as session:
            result = await session.execute(select(TripExportJob).where(TripExportJob.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                job.status = ExportJobStatus.FAILED
                job.updated_at_utc = _now_utc()
                job.completed_at_utc = _now_utc()
                await session.commit()
