from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from ulid import ULID

from auth_service.broker import EventBroker
from auth_service.config import settings
from auth_service.database import async_session_factory
from auth_service.models import AuthOutboxModel, AuthUserModel
from auth_service.workers.outbox_relay import _process_batch


def _new_ulid() -> str:
    return str(ULID())


class RecordingBroker(EventBroker):
    def __init__(self, *, failing_event_names: set[str] | None = None) -> None:
        self.failing_event_names = failing_event_names or set()
        self.published: list[tuple[str, str, dict[str, object]]] = []

    async def publish(self, topic: str, key: str, payload: dict) -> None:
        if str(payload.get("event_name")) in self.failing_event_names:
            raise RuntimeError(f"publish failed for {payload['event_name']}")
        self.published.append((topic, key, payload))

    async def close(self) -> None:
        return None

    async def check_health(self) -> None:
        pass

    async def probe(self) -> tuple[bool, str | None]:
        return True, None


async def _bootstrap_user() -> AuthUserModel:
    async with async_session_factory() as session:
        result = await session.execute(
            sa.select(AuthUserModel).where(
                AuthUserModel.username == "bootstrap-admin"
            )
        )
        return result.scalar_one()


async def _insert_outbox_row(
    *,
    aggregate_id: str,
    event_name: str,
    publish_status: str = "PENDING",
    retry_count: int = 0,
    next_attempt_at_utc: datetime | None = None,
    claim_expires_at_utc: datetime | None = None,
) -> str:
    outbox_id = _new_ulid()
    async with async_session_factory() as session:
        session.add(
            AuthOutboxModel(
                outbox_id=outbox_id,
                aggregate_type="USER",
                aggregate_id=aggregate_id,
                event_name=event_name,
                event_version=1,
                payload_json='{"user_id": "%s"}' % aggregate_id,
                publish_status=publish_status,
                retry_count=retry_count,
                last_error=None,
                created_at_utc=datetime.now(UTC),
                next_attempt_at_utc=next_attempt_at_utc or datetime.now(UTC),
                claim_expires_at_utc=claim_expires_at_utc,
                published_at_utc=None,
            )
        )
        await session.commit()
    return outbox_id


@pytest.mark.asyncio
async def test_outbox_reclaims_stale_publishing_rows() -> None:
    user = await _bootstrap_user()
    outbox_id = await _insert_outbox_row(
        aggregate_id=user.user_id,
        event_name="identity.user.created.v1",
        publish_status="PUBLISHING",
        next_attempt_at_utc=datetime.now(UTC) - timedelta(seconds=30),
        claim_expires_at_utc=datetime.now(UTC) - timedelta(seconds=1),
    )
    broker = RecordingBroker()

    published_count = await _process_batch(broker)

    assert published_count == 1
    assert len(broker.published) == 1
    async with async_session_factory() as session:
        row = await session.get(AuthOutboxModel, outbox_id)
    assert row is not None
    assert row.publish_status == "PUBLISHED"
    assert row.claim_expires_at_utc is None
    assert row.last_error is None


@pytest.mark.asyncio
async def test_outbox_failure_does_not_roll_back_other_rows() -> None:
    user = await _bootstrap_user()
    failed_id = await _insert_outbox_row(
        aggregate_id=user.user_id,
        event_name="identity.user.failed.v1",
    )
    published_id = await _insert_outbox_row(
        aggregate_id=user.user_id,
        event_name="identity.user.updated.v1",
    )
    broker = RecordingBroker(failing_event_names={"identity.user.failed.v1"})

    published_count = await _process_batch(broker)

    assert published_count == 1
    async with async_session_factory() as session:
        failed_row = await session.get(AuthOutboxModel, failed_id)
        published_row = await session.get(AuthOutboxModel, published_id)
    assert failed_row is not None
    assert failed_row.publish_status == "FAILED"
    assert (
        failed_row.last_error
        == "RuntimeError: publish failed for identity.user.failed.v1"
    )
    assert published_row is not None
    assert published_row.publish_status == "PUBLISHED"


@pytest.mark.asyncio
async def test_outbox_dead_letters_at_retry_ceiling() -> None:
    user = await _bootstrap_user()
    outbox_id = await _insert_outbox_row(
        aggregate_id=user.user_id,
        event_name="identity.user.dead-letter.v1",
        retry_count=settings.outbox_retry_max - 1,
    )
    broker = RecordingBroker(failing_event_names={"identity.user.dead-letter.v1"})

    published_count = await _process_batch(broker)

    assert published_count == 0
    async with async_session_factory() as session:
        row = await session.get(AuthOutboxModel, outbox_id)
    assert row is not None
    assert row.publish_status == "DEAD_LETTER"
    assert row.claim_expires_at_utc is None
    assert (
        row.last_error
        == "RuntimeError: publish failed for identity.user.dead-letter.v1"
    )
