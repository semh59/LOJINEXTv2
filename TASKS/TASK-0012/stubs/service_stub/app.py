from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class FleetValidationRequest(BaseModel):
    driver_id: str
    vehicle_id: str | None = None
    trailer_id: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/v1/trip-references/validate")
def validate_trip_references(payload: FleetValidationRequest) -> dict[str, bool | None]:
    driver_valid = payload.driver_id.strip().lower() != "invalid"
    vehicle_valid = None if payload.vehicle_id is None else payload.vehicle_id.strip().lower() != "invalid"
    trailer_valid = None if payload.trailer_id is None else payload.trailer_id.strip().lower() != "invalid"
    return {
        "driver_valid": driver_valid,
        "vehicle_valid": vehicle_valid,
        "trailer_valid": trailer_valid,
    }

