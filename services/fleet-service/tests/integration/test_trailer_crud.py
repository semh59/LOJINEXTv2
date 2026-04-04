import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS, SUPER_ADMIN_HEADERS


@pytest.mark.asyncio
async def test_trailer_full_crud_lifecycle(client: AsyncClient):
    # Mirror of vehicle CRUD
    create_payload = {
        "asset_code": "T-501",
        "plate": "34 TR 555",
        "ownership_type": "LEASED",
        "brand": "Tirsan",
        "model": "Maxima",
        "model_year": 2022,
    }

    headers = {**ADMIN_HEADERS, "X-Idempotency-Key": "idem-trailer-001"}
    resp = await client.post("/api/v1/trailers", json=create_payload, headers=headers)
    assert resp.status_code == 201
    trailer_id = resp.json()["trailer_id"]
    etag = resp.headers["ETag"]

    # PATCH
    resp = await client.patch(
        f"/api/v1/trailers/{trailer_id}", json={"notes": "Updated note"}, headers={**ADMIN_HEADERS, "If-Match": etag}
    )
    assert resp.status_code == 200
    new_etag = resp.headers["ETag"]

    # Soft Delete
    resp = await client.post(
        f"/api/v1/trailers/{trailer_id}/soft-delete",
        json={"reason": "Scrapped"},
        headers={**ADMIN_HEADERS, "If-Match": new_etag},
    )
    assert resp.status_code == 200
    soft_etag = resp.headers["ETag"]

    # Hard Delete
    resp = await client.request(
        "DELETE",
        f"/api/v1/trailers/{trailer_id}",
        json={"reason": "Audit cleanup"},
        headers={**SUPER_ADMIN_HEADERS, "If-Match": soft_etag},
    )
    assert resp.status_code == 200
