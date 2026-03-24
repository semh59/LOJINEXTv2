import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.models import LocationPoint


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    """Test the liveness probe."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_endpoint(client: AsyncClient) -> None:
    """Test the readiness probe to verify database connectivity."""
    response = await client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    # Mapbox key might be missing in test env, so it might say "not_ready" overall
    # But database check must be "ok" since testcontainers is running
    assert data["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_create_location_point(test_session: AsyncSession) -> None:
    """Deep test: verify we can insert a LocationPoint and constraints hold."""
    point = LocationPoint(
        code="TR_IST_01",
        name_tr="İstanbul Depo",
        name_en="Istanbul Warehouse",
        normalized_name_tr="ISTANBUL DEPO",
        normalized_name_en="ISTANBUL WAREHOUSE",
        latitude_6dp=41.0082,
        longitude_6dp=28.9784,
        is_active=True,
    )
    test_session.add(point)
    await test_session.commit()

    # Query back
    result = await test_session.execute(select(LocationPoint).where(LocationPoint.code == "TR_IST_01"))
    saved_point = result.scalar_one()

    assert saved_point.location_id is not None
    assert saved_point.latitude_6dp == 41.0082
    assert saved_point.longitude_6dp == 28.9784
    assert saved_point.row_version == 1

    await test_session.close()
