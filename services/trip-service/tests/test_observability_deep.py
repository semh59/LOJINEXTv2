"""Deep tests for cleanup jobs and structured observability."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from platform_common import OutboxPublishStatus
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

import trip_service.observability as observability
from trip_service.models import TripIdempotencyRecord, TripOutbox

pytestmark = [pytest.mark.runtime, pytest.mark.dbgate]


def _dbapi_error(message: str) -> DBAPIError:
    return DBAPIError("SELECT 1", {}, Exception(message), False)


def test_setup_logging_emits_structured_json(capsys: pytest.CaptureFixture[str]) -> None:
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level

    try:
        observability.setup_logging("DEBUG")
        logger = logging.getLogger("trip_service.tests.logging")
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.error("structured-message", extra={"request_id": "req-123"}, exc_info=True)

        output = capsys.readouterr().out.strip()
        payload = json.loads(output)
        assert payload["service"] == observability.settings.service_name
        assert payload["level"] == "ERROR"
        assert payload["message"] == "structured-message"
        assert payload["request_id"] == "req-123"
        assert "RuntimeError: boom" in payload["exception"]
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)


def test_cleanup_schema_not_ready_detection() -> None:
    assert observability._is_schema_not_ready(_dbapi_error("relation trip_outbox does not exist")) is True
    assert observability._is_schema_not_ready(_dbapi_error("relation other_table does not exist")) is False
    assert observability._is_schema_not_ready(RuntimeError("not dbapi")) is False


@pytest.mark.asyncio
async def test_cleanup_idempotency_records_deletes_only_expired_rows(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(observability, "async_session_factory", session_factory)
    now = datetime.now(UTC)

    async with session_factory() as session:
        session.add(
            TripIdempotencyRecord(
                idempotency_key="expired-key",
                endpoint_fingerprint="trip:create",
                request_hash="hash-1",
                response_status=201,
                response_headers_json={},
                response_body_json="{}",
                created_at_utc=now - timedelta(days=2),
                expires_at_utc=now - timedelta(minutes=5),
            )
        )
        session.add(
            TripIdempotencyRecord(
                idempotency_key="fresh-key",
                endpoint_fingerprint="trip:create",
                request_hash="hash-2",
                response_status=201,
                response_headers_json={},
                response_body_json="{}",
                created_at_utc=now,
                expires_at_utc=now + timedelta(hours=1),
            )
        )
        await session.commit()

    deleted = await observability.cleanup_idempotency_records()

    assert deleted == 1
    async with session_factory() as session:
        remaining = await session.get(
            TripIdempotencyRecord,
            {"idempotency_key": "fresh-key", "endpoint_fingerprint": "trip:create"},
        )
    assert remaining is not None


@pytest.mark.asyncio
async def test_cleanup_outbox_records_applies_retention_cutoffs(db_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(observability, "async_session_factory", session_factory)
    now = datetime.now(UTC)
    published_id = "A" * 26
    dead_letter_id = "B" * 26
    fresh_id = "C" * 26

    async with session_factory() as session:
        session.add(
            TripOutbox(
                event_id=published_id,
                aggregate_type="TRIP",
                aggregate_id="trip-001",
                aggregate_version=1,
                event_name="trip.created.v1",
                schema_version=1,
                payload_json="{}",
                partition_key="trip-001",
                publish_status=OutboxPublishStatus.PUBLISHED,
                attempt_count=0,
                created_at_utc=now - timedelta(days=40),
                published_at_utc=now - timedelta(days=35),
            )
        )
        session.add(
            TripOutbox(
                event_id=dead_letter_id,
                aggregate_type="TRIP",
                aggregate_id="trip-002",
                aggregate_version=1,
                event_name="trip.created.v1",
                schema_version=1,
                payload_json="{}",
                partition_key="trip-002",
                publish_status=OutboxPublishStatus.DEAD_LETTER,
                attempt_count=10,
                created_at_utc=now - timedelta(days=100),
            )
        )
        session.add(
            TripOutbox(
                event_id=fresh_id,
                aggregate_type="TRIP",
                aggregate_id="trip-003",
                aggregate_version=1,
                event_name="trip.created.v1",
                schema_version=1,
                payload_json="{}",
                partition_key="trip-003",
                publish_status=OutboxPublishStatus.PUBLISHED,
                attempt_count=0,
                created_at_utc=now,
                published_at_utc=now,
            )
        )
        await session.commit()

    deleted = await observability.cleanup_outbox_records()

    assert deleted == 2
    async with session_factory() as session:
        fresh = await session.get(TripOutbox, fresh_id)
        old_published = await session.get(TripOutbox, published_id)
        old_dead_letter = await session.get(TripOutbox, dead_letter_id)

    assert fresh is not None
    assert old_published is None
    assert old_dead_letter is None


@pytest.mark.asyncio
async def test_run_cleanup_loop_warns_on_schema_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_cleanup() -> int:
        raise _dbapi_error("relation trip_outbox does not exist")

    async def stop_sleep(worker_name: str, interval_seconds: int) -> None:
        del worker_name, interval_seconds
        raise asyncio.CancelledError

    warnings: list[str] = []

    def fake_warning(message: str, *args) -> None:
        warnings.append(message % args if args else message)

    monkeypatch.setattr(observability, "cleanup_idempotency_records", fail_cleanup)
    monkeypatch.setattr(observability, "_sleep_with_heartbeats", stop_sleep)
    monkeypatch.setattr(observability.logger, "warning", fake_warning)

    with pytest.raises(asyncio.CancelledError):
        await observability.run_cleanup_loop(interval_seconds=1)

    assert warnings == ["Cleanup skipped because the trip schema is not migrated yet"]


@pytest.mark.asyncio
async def test_run_cleanup_loop_logs_generic_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_cleanup() -> int:
        raise RuntimeError("cleanup exploded")

    async def stop_sleep(worker_name: str, interval_seconds: int) -> None:
        del worker_name, interval_seconds
        raise asyncio.CancelledError

    errors: list[str] = []

    def fake_error(message: str, *args) -> None:
        errors.append(message % args if args else message)

    monkeypatch.setattr(observability, "cleanup_idempotency_records", fail_cleanup)
    monkeypatch.setattr(observability, "_sleep_with_heartbeats", stop_sleep)
    monkeypatch.setattr(observability.logger, "error", fake_error)

    with pytest.raises(asyncio.CancelledError):
        await observability.run_cleanup_loop(interval_seconds=1)

    assert errors == ["Cleanup error: cleanup exploded"]
