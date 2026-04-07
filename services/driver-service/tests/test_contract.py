"""Contract tests for Outbox events and Trip client (spec section 18)."""

import json
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from conftest import TEST_JWKS_BUNDLE
from httpx import AsyncClient
from platform_auth_testing import sign_test_token
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driver_service.auth import issue_internal_service_token, require_internal_service_token
from driver_service.config import settings
from driver_service.errors import ProblemDetailError
from driver_service.models import DriverOutboxModel


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


def _service_token(payload: dict[str, object]) -> str:
    """Build a service token signed the same way as the runtime auth helpers."""
    return sign_test_token(
        TEST_JWKS_BUNDLE,
        sub=str(payload["sub"]),
        role=str(payload["role"]),
        service=str(payload["service"]) if payload.get("service") is not None else None,
        aud=str(payload["aud"]) if payload.get("aud") is not None else settings.auth_audience,
    )


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
    DriverCreatedEvent.model_validate(event_data)


@pytest.mark.asyncio
async def test_trip_client_check_usage():
    """Driver maintenance must use the generic Trip asset-reference contract."""
    import httpx

    from driver_service.routers.maintenance import _check_trip_references

    driver_id = "01HYY"
    mock_response = httpx.Response(
        200,
        json={"asset_type": "DRIVER", "asset_id": driver_id, "is_referenced": True, "active_trip_count": 1},
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await _check_trip_references(driver_id)

    assert result is False
    assert mock_post.await_args.kwargs["json"] == {"asset_id": driver_id, "asset_type": "DRIVER"}


@pytest.mark.asyncio
async def test_issue_internal_service_token_uses_service_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outbound tokens must be fetched from identity-service with SERVICE role semantics."""

    async def fake_get_token(**kwargs) -> str:
        return sign_test_token(
            TEST_JWKS_BUNDLE,
            sub=kwargs["service_name"],
            role="SERVICE",
            service=kwargs["client_id"],
            aud=kwargs["audience"],
        )

    monkeypatch.setattr("driver_service.auth._SERVICE_TOKEN_CACHE.get_token", fake_get_token)

    token = await issue_internal_service_token(audience="trip-service")
    payload = jwt.decode(
        token,
        TEST_JWKS_BUNDLE.public_key_pem,
        algorithms=["RS256"],
        audience="trip-service",
        issuer=settings.auth_issuer,
    )

    assert payload["sub"] == settings.service_name
    assert payload["role"] == "SERVICE"
    assert payload["service"] == settings.service_name
    assert payload["aud"] == "trip-service"


def test_require_internal_service_token_rejects_unapproved_service() -> None:
    """Driver internal endpoints should reject unknown service callers."""
    token = _service_token({"sub": "rogue-service", "role": "SERVICE", "service": "rogue-service"})

    with pytest.raises(ProblemDetailError) as exc_info:
        require_internal_service_token(f"Bearer {token}")

    assert exc_info.value.code == "DRIVER_INTERNAL_FORBIDDEN"
