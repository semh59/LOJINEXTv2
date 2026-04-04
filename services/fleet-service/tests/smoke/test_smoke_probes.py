import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_probes(client: AsyncClient):
    # Liveness
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

    # Readiness
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["database"] == "connected"
