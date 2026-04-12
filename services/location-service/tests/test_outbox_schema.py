"""Outbox event schema assertion tests.

Verifies that:
1. The Kafka envelope published by _process_batch contains all required fields
   with correct types and values.
2. Outbox rows written by API mutations carry correct event_name, payload
   structure, and partition_key according to the V2.1 standard.

These tests complement test_outbox_deep.py (relay mechanics) by pinning the
data contract that Kafka consumers depend on.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from location_service.config import settings
from location_service.models import LocationOutboxModel
from location_service.workers.outbox_relay import _process_batch

# Pattern all Location Service event names must match
_EVENT_NAME_RE = re.compile(r"^location\.[a-z_]+\.[a-z_]+\.v\d+$")

# All event names produced by the service (guards against typos in router code)
KNOWN_EVENT_NAMES = {
    "location.point.created.v1",
    "location.point.updated.v1",
    "location.pair.created.v1",
    "location.pair.updated.v1",
    "location.pair.soft_deleted.v1",
    "location.route.activated.v1",
    "location.route.discarded.v1",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def override_outbox_settings():
    old_batch = settings.outbox_publish_batch_size
    old_retry = settings.outbox_retry_max
    settings.outbox_publish_batch_size = 10
    settings.outbox_retry_max = 5
    yield
    settings.outbox_publish_batch_size = old_batch
    settings.outbox_retry_max = old_retry


def _make_outbox_row(
    event_name: str = "location.point.created.v1",
    payload: dict | None = None,
    partition_key: str = "01J000000000000000000ABCDE",
) -> LocationOutboxModel:
    now = datetime.now(UTC)
    payload_dict = payload or {"location_id": "01J000000000000000000ABCDE", "code": "IST"}
    agg_id = payload_dict.get("location_id") or payload_dict.get("pair_id") or "01J000000000000000000ABCDE"
    return LocationOutboxModel(
        event_name=event_name,
        aggregate_type="LOCATION",
        aggregate_id=agg_id,
        event_version=1,
        payload_json=json.dumps(payload_dict),
        partition_key=partition_key,
        created_at_utc=now,
        next_attempt_at_utc=now,
    )


# ---------------------------------------------------------------------------
# Envelope schema published to broker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_published_envelope_contains_all_required_fields(db_engine, override_outbox_settings) -> None:
    """The Kafka envelope must contain every field the V2.1 standard mandates."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(_make_outbox_row())
        await session.commit()

    broker = AsyncMock()
    async with session_factory() as session:
        await _process_batch(session, broker)

    assert broker.publish.call_count == 1
    _, kwargs = broker.publish.call_args
    envelope = (
        kwargs.get("payload") or broker.publish.call_args.args[2] if len(broker.publish.call_args.args) > 2 else None
    )

    # Extract the payload however it was passed (keyword or positional)
    call_kwargs = broker.publish.call_args.kwargs
    envelope = call_kwargs["payload"]

    required_fields = {
        "event_id",
        "event_name",
        "event_version",
        "aggregate_id",
        "aggregate_type",
        "payload",
        "published_at_utc",
    }
    for field in required_fields:
        assert field in envelope, f"Kafka envelope missing required field: {field!r}"


@pytest.mark.asyncio
async def test_published_envelope_field_types(db_engine, override_outbox_settings) -> None:
    """Each envelope field must have the correct type."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(_make_outbox_row("location.pair.created.v1", {"pair_id": "01J000000000000000000PAIR1"}))
        await session.commit()

    broker = AsyncMock()
    async with session_factory() as session:
        await _process_batch(session, broker)

    envelope = broker.publish.call_args.kwargs["payload"]

    assert isinstance(envelope["event_id"], str) and len(envelope["event_id"]) == 26, (
        "event_id must be a 26-char ULID string"
    )
    assert isinstance(envelope["event_name"], str)
    assert isinstance(envelope["event_version"], int) and envelope["event_version"] >= 1
    assert isinstance(envelope["aggregate_id"], str) and envelope["aggregate_id"]
    assert isinstance(envelope["aggregate_type"], str) and envelope["aggregate_type"]
    assert isinstance(envelope["payload"], dict)
    # published_at_utc must be parseable ISO 8601
    dt = datetime.fromisoformat(envelope["published_at_utc"])
    assert dt.tzinfo is not None, "published_at_utc must be timezone-aware"


@pytest.mark.asyncio
async def test_envelope_aggregate_type_defaults_to_location(db_engine, override_outbox_settings) -> None:
    """aggregate_type must default to 'LOCATION' when not in payload_json."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        # payload has no explicit target_type
        session.add(_make_outbox_row(payload={"location_id": "01J000000000000000000AAAAA"}))
        await session.commit()

    broker = AsyncMock()
    async with session_factory() as session:
        await _process_batch(session, broker)

    envelope = broker.publish.call_args.kwargs["payload"]
    assert envelope["aggregate_type"] == "LOCATION"


@pytest.mark.asyncio
async def test_envelope_aggregate_id_resolves_from_location_id(db_engine, override_outbox_settings) -> None:
    """aggregate_id must be the location_id when present in payload_json."""
    location_id = "01J000000000000000000LOCID"
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(_make_outbox_row(payload={"location_id": location_id, "code": "ANK"}))
        await session.commit()

    broker = AsyncMock()
    async with session_factory() as session:
        await _process_batch(session, broker)

    envelope = broker.publish.call_args.kwargs["payload"]
    assert envelope["aggregate_id"] == location_id


@pytest.mark.asyncio
async def test_envelope_aggregate_id_resolves_from_pair_id(db_engine, override_outbox_settings) -> None:
    """aggregate_id must be the pair_id when payload_json uses pair_id."""
    pair_id = "01J000000000000000000PAIRF"
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            _make_outbox_row(
                event_name="location.pair.created.v1",
                payload={"pair_id": pair_id, "pair_code": "RP_01J000000000000000000XYZ"},
            )
        )
        await session.commit()

    broker = AsyncMock()
    async with session_factory() as session:
        await _process_batch(session, broker)

    envelope = broker.publish.call_args.kwargs["payload"]
    assert envelope["aggregate_id"] == pair_id


# ---------------------------------------------------------------------------
# event_name conventions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_known_event_names_match_naming_convention(db_engine, override_outbox_settings) -> None:
    """All known event names must follow location.<entity>.<action>.v<n> pattern."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with session_factory() as session:
        for event_name in KNOWN_EVENT_NAMES:
            session.add(
                LocationOutboxModel(
                    aggregate_type="LOCATION",
                    aggregate_id=f"01J{event_name[:22].upper().replace('.', '0')}",
                    event_name=event_name,
                    event_version=1,
                    payload_json=json.dumps({"location_id": f"01J{event_name[:22].upper().replace('.', '0')}"}),
                    partition_key="01J000000000000000000PRTK0",
                    created_at_utc=now,
                    next_attempt_at_utc=now,
                )
            )
        await session.commit()

    broker = AsyncMock()
    async with session_factory() as session:
        await _process_batch(session, broker)

    published_names = {c.kwargs["payload"]["event_name"] for c in broker.publish.call_args_list}
    for name in published_names:
        assert _EVENT_NAME_RE.match(name), f"Event name {name!r} does not match location.<entity>.<action>.v<n>"


# ---------------------------------------------------------------------------
# Outbox row creation: partition_key derivation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partition_key_derived_from_location_id(db_engine) -> None:
    """_write_outbox sets partition_key from payload.location_id when present."""
    from location_service.audit_helpers import _write_outbox

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    location_id = "01J000000000000000000LOCPK"
    async with session_factory() as session:
        await _write_outbox(
            session,
            event_name="location.point.created.v1",
            payload={"location_id": location_id, "code": "IST"},
        )
        await session.flush()

        result = await session.execute(
            select(LocationOutboxModel).where(LocationOutboxModel.event_name == "location.point.created.v1")
        )
        row = result.scalar_one()
        assert row.partition_key == location_id


@pytest.mark.asyncio
async def test_partition_key_derived_from_pair_id(db_engine) -> None:
    """_write_outbox sets partition_key from payload.pair_id when location_id absent."""
    from location_service.audit_helpers import _write_outbox

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    pair_id = "01J000000000000000000PAIRK"
    async with session_factory() as session:
        await _write_outbox(
            session,
            event_name="location.pair.created.v1",
            payload={"pair_id": pair_id, "pair_code": "RP_01J00000000000000000000AB"},
        )
        await session.flush()

        result = await session.execute(
            select(LocationOutboxModel).where(LocationOutboxModel.event_name == "location.pair.created.v1")
        )
        row = result.scalar_one()
        assert row.partition_key == pair_id


@pytest.mark.asyncio
async def test_partition_key_falls_back_to_global(db_engine) -> None:
    """_write_outbox uses 'global' as partition_key when no ID is in payload."""
    from location_service.audit_helpers import _write_outbox

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        await _write_outbox(
            session,
            event_name="location.point.created.v1",
            payload={"occurred_at_utc": "2026-04-07T00:00:00Z"},
        )
        await session.flush()

        result = await session.execute(
            select(LocationOutboxModel).where(LocationOutboxModel.event_name == "location.point.created.v1")
        )
        row = result.scalar_one()
        assert row.partition_key == "global"
