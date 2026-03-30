"""Contract tests for Outbox events and Trip client (spec §18)."""

import json

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driver_service.models import DriverOutboxModel

# ---------------------------------------------------------------------------
# EVENT SCHEMAS (BR-CONTRACT)
# ---------------------------------------------------------------------------


class DriverCreatedEvent(BaseModel):
    driver_id: str
    company_driver_code: str | None
    phone_e164: str | None
    telegram_user_id: str | None
    license_class: str
    status: str
    row_version: int
    created_at_utc: str


class DriverUpdatedEvent(BaseModel):
    driver_id: str
    changed_fields: list[str]
    row_version: int
    updated_at_utc: str


# ---------------------------------------------------------------------------
# EVENT SCHEMA VALIDATION TESTS
# ---------------------------------------------------------------------------


from httpx import AsyncClient


@pytest.mark.asyncio
async def test_event_schema_driver_created(client: AsyncClient, auth_admin: dict[str, str], db_session: AsyncSession):
    """Verify driver.created.v1 schema matches expectations by checking the outbox."""
    payload = {
        "full_name": "Event Test Driver",
        "phone": "+905557778899",
        "telegram_user_id": "event_tg",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    assert resp.status_code == 201
    driver_id = resp.json()["driver_id"]

    query = select(DriverOutboxModel).where(
        DriverOutboxModel.driver_id == driver_id, DriverOutboxModel.event_name == "driver.created.v1"
    )
    result = await db_session.execute(query)
    outbox_row = result.scalars().first()

    assert outbox_row is not None
    event_data = json.loads(outbox_row.payload_json)

    # Validate payload against schema (will raise ValidationError if invalid)
    DriverCreatedEvent.model_validate(event_data)


# ---------------------------------------------------------------------------
# TRIP SERVICE CLIENT CONTRACT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trip_client_check_usage():
    """Contract test: Driver-Trip reference check schema."""
    from unittest.mock import patch

    import httpx

    from driver_service.routers.maintenance import _check_trip_references

    driver_id = "01HYY"
    mock_response = httpx.Response(
        200, json={"driver_id": driver_id, "has_references": True, "safe_to_delete": True, "active_trip_count": 1}
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await _check_trip_references(driver_id)
        assert result is True
