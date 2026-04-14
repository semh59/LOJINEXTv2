"""Internal Pydantic models for telegram-service."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class SlipFields(BaseModel):
    """Parsed fields extracted from a slip photo via OCR."""

    truck_plate: str | None = None
    trailer_plate: str | None = None
    origin: str | None = None
    destination: str | None = None
    trip_date: str | None = None  # DD.MM.YYYY
    trip_time: str | None = None  # HH:MM
    tare_kg: int | None = None
    gross_kg: int | None = None
    net_kg: int | None = None
    slip_no: str | None = None  # Weighing slip NO field (e.g. 40226)
    raw_text: str = ""
    ocr_confidence: float = 0.0  # Ratio of filled fields (0.0 – 1.0)

    model_config = ConfigDict(frozen=False)

    def filled_count(self) -> int:
        """Return number of non-None data fields."""
        fields = [
            self.truck_plate, self.origin, self.destination,
            self.trip_date, self.tare_kg, self.gross_kg, self.net_kg,
        ]
        return sum(1 for f in fields if f is not None)

    def compute_confidence(self) -> float:
        """Compute confidence as ratio of filled mandatory fields."""
        total = 7  # truck_plate, origin, destination, date, tare, gross, net
        return self.filled_count() / total


class DriverLookupResult(BaseModel):
    """Minimal driver info returned by driver-service lookup."""

    driver_id: str
    full_name: str
    telegram_user_id: str | None = None
    status: str
    is_assignable: bool


class TripIngestResult(BaseModel):
    """Response from trip-service slip ingest endpoints."""

    id: str
    trip_no: str
    status: str
    source_type: str

    model_config = ConfigDict(extra="ignore")


class StatementRow(BaseModel):
    """One trip row in the driver statement."""

    date: str
    hour: str
    truck_plate: str
    origin: str = ""
    destination: str = ""
    net_weight_kg: int
    tare_weight_kg: int = 0
    gross_weight_kg: int = 0
    fee: str = ""
    approval: str = ""
    slip_no: str = ""  # Weighing slip NO (e.g. 40226), used as card NO field

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @classmethod
    def from_trip_service_row(cls, row: dict[str, Any]) -> "StatementRow":
        return cls(
            date=row.get("date", ""),
            hour=row.get("hour", ""),
            truck_plate=row.get("truck_plate", ""),
            origin=row.get("from", ""),
            destination=row.get("to", ""),
            net_weight_kg=row.get("net_weight_kg", 0),
            tare_weight_kg=row.get("tare_weight_kg", 0),
            gross_weight_kg=row.get("gross_weight_kg", 0),
            fee=row.get("fee", ""),
            approval=row.get("approval", ""),
            slip_no=row.get("source_slip_no") or row.get("trip_no", ""),
        )


class StatementRequest(BaseModel):
    """Date range selection for driver statement PDF."""

    date_from: date
    date_to: date
