import datetime

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS


@pytest.mark.asyncio
async def test_vehicle_spec_versioning_flow(client: AsyncClient):
    # 1. Create a vehicle first
    headers = {**ADMIN_HEADERS, "X-Idempotency-Key": "spec-test-v1"}
    create_resp = await client.post(
        "/api/v1/vehicles",
        json={
            "asset_code": "V-SPEC-01",
            "plate": "34 SPEC 01",
            "ownership_type": "OWNED",
            "initial_spec": {
                "change_reason": "Factory defaults",
                "fuel_type": "DIESEL",
                "powertrain_type": "ICE",
                "gvwr_kg": 18000,
            },
        },
        headers=headers,
    )
    vehicle_id = create_resp.json()["vehicle_id"]
    spec_etag = create_resp.headers["X-Spec-ETag"]  # Initial spec ETag (sv0)

    # 2. GET current spec
    resp = await client.get(f"/api/v1/vehicles/{vehicle_id}/specs/current", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["version_no"] == 1
    assert resp.json()["gvwr_kg"] == 18000.0

    # 3. Create new spec version (Version 2)
    # effective_from_utc in the past relative to 'now' to test temporal query later
    v2_effective = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()

    new_spec_payload = {
        "change_reason": "Engine upgrade",
        "effective_from_utc": v2_effective,
        "fuel_type": "DIESEL",
        "powertrain_type": "ICE",
        "engine_power_kw": 350.5,
        "gvwr_kg": 18000,
    }

    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/specs", json=new_spec_payload, headers={**ADMIN_HEADERS, "If-Match": spec_etag}
    )
    assert resp.status_code == 201
    v2_spec_etag = resp.headers["ETag"]
    assert "sv1" in v2_spec_etag

    # 4. Verify version 2 is current
    resp = await client.get(f"/api/v1/vehicles/{vehicle_id}/specs/current", headers=ADMIN_HEADERS)
    assert resp.json()["version_no"] == 2
    assert resp.json()["engine_power_kw"] == 350.5

    # 5. AS-OF query (Check Version 1 state)
    # We query for 'now', which is before Version 2 becomes effective
    past_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    resp = await client.get(f"/api/v1/vehicles/{vehicle_id}/specs/as-of?at={past_ts}", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["version_no"] == 1
    assert resp.json()["engine_power_kw"] is None

    # 6. Overlap detection (GiST)
    # Try to insert a version with same effective_from as version 2
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/specs",
        json={**new_spec_payload, "change_reason": "Conflict"},
        headers={**ADMIN_HEADERS, "If-Match": v2_spec_etag},
    )
    assert resp.status_code == 409
    assert "overlap" in resp.text.lower()


@pytest.mark.asyncio
async def test_spec_temporal_gaps(client: AsyncClient):
    # 1. Create vehicle
    v_resp = await client.post(
        "/api/v1/vehicles",
        json={
            "asset_code": "V-GAP-01",
            "plate": "34 GAP 01",
            "ownership_type": "OWNED",
            "initial_spec": {"change_reason": "v1", "gvwr_kg": 10000},
        },
        headers={**ADMIN_HEADERS, "X-Idempotency-Key": "gap-test-v1"},
    )
    vehicle_id = v_resp.json()["vehicle_id"]
    spec_etag = v_resp.headers["X-Spec-ETag"]

    # 2. Add version 2 with a GAP (effective 2 days from now)
    now = datetime.datetime.now(datetime.timezone.utc)
    v2_start = now + datetime.timedelta(days=2)

    # Actually, the 'close_current_spec' repo method sets effective_to of previous to the NEW effective_from.
    # So gaps are technically not possible via the standard API unless manually manipulated or if we test
    # the behavior of overlapping/gaps if we HAD them.
    # But wait, create_vehicle_spec_version does:
    # await vehicle_spec_repo.close_current_spec(session, vehicle_id, effective_from)
    # This ensures NO GAPS between current and new.

    # Let's test if we can retrieve at a specific point in history correctly.
    v2_resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/specs",
        json={"change_reason": "v2", "gvwr_kg": 20000, "effective_from_utc": v2_start.isoformat()},
        headers={**ADMIN_HEADERS, "If-Match": spec_etag},
    )
    assert v2_resp.status_code == 201

    # Query exactly at now -> should be V1
    resp_v1 = await client.get(f"/api/v1/vehicles/{vehicle_id}/specs/as-of?at={now.isoformat()}", headers=ADMIN_HEADERS)
    assert resp_v1.json()["version_no"] == 1

    # Query at V2 start -> should be V2
    resp_v2 = await client.get(
        f"/api/v1/vehicles/{vehicle_id}/specs/as-of?at={v2_start.isoformat()}", headers=ADMIN_HEADERS
    )
    assert resp_v2.json()["version_no"] == 2


@pytest.mark.asyncio
async def test_transactional_rollback_on_spec_conflict(client: AsyncClient, test_session):
    # We want to ensure that if a spec creation fails (e.g. overlap),
    # NO timeline events or outbox events are committed for that failed attempt.

    # 1. Create vehicle
    v_resp = await client.post(
        "/api/v1/vehicles",
        json={
            "asset_code": "V-ROLL-01",
            "plate": "34 ROLL 01",
            "ownership_type": "OWNED",
            "initial_spec": {"change_reason": "v1"},
        },
        headers={**ADMIN_HEADERS, "X-Idempotency-Key": "roll-test-v1"},
    )
    vehicle_id = v_resp.json()["vehicle_id"]
    spec_etag = v_resp.headers["X-Spec-ETag"]

    # 2. Trigger conflict (overlap)
    # Use same effective_from as version 1 (which was the vehicle creation time)
    now = datetime.datetime.now(datetime.timezone.utc)

    from sqlalchemy import func, select

    from fleet_service.models import FleetAssetTimelineEvent, FleetOutbox

    # Count current outbox/timeline for this vehicle
    async def get_counts():
        o_cnt = await test_session.scalar(
            select(func.count()).select_from(FleetOutbox).where(FleetOutbox.aggregate_id == vehicle_id)
        )
        t_cnt = await test_session.scalar(
            select(func.count())
            .select_from(FleetAssetTimelineEvent)
            .where(FleetAssetTimelineEvent.aggregate_id == vehicle_id)
        )
        return o_cnt, t_cnt

    base_o, base_t = await get_counts()

    # Try to create conflicting spec
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/specs",
        json={"change_reason": "conflict", "effective_from_utc": now.isoformat()},
        headers={**ADMIN_HEADERS, "If-Match": spec_etag},
    )
    assert resp.status_code == 409

    # 3. Verify counts haven't changed
    new_o, new_t = await get_counts()
    assert new_o == base_o
    assert new_t == base_t
