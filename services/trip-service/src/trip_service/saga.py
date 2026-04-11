"""SAGA orchestrator for complex trip booking lifecycles."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ulid import ULID

from trip_service.broker import OutboxMessage, create_broker
from trip_service.config import settings
from trip_service.redis_client import get_redis

logger = logging.getLogger("trip_service.saga")

_SAGA_KEY_TTL_SECONDS = 86_400  # 24 hours


class SagaStatus(Enum):
    PENDING = "PENDING"
    COMPLETING = "COMPLETING"
    COMPENSATING = "COMPENSATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class _CompensateStep(Enum):
    RELEASE_VEHICLE = "RELEASE_VEHICLE"
    RELEASE_DRIVER = "RELEASE_DRIVER"
    MARK_TRIP_FAILED = "MARK_TRIP_FAILED"


class TripBookingSagaOrchestrator:
    """Manages the distributed transaction for booking a trip."""

    def __init__(self, trip_id: str) -> None:
        self.trip_id = trip_id
        self.redis_key = f"saga:trip_booking:{trip_id}"

    async def _update_status(self, status: SagaStatus) -> None:
        redis = await get_redis()
        async with redis.pipeline(transaction=True) as pipe:
            pipe.hset(self.redis_key, "status", status.value)
            pipe.expire(self.redis_key, _SAGA_KEY_TTL_SECONDS)
            await pipe.execute()
        logger.info("SAGA [%s] status updated to %s", self.trip_id, status.value)

    async def _record_step(self, step: _CompensateStep, outcome: str) -> None:
        """Persist the outcome of a single compensation step in Redis."""
        redis = await get_redis()
        await redis.hset(self.redis_key, f"step:{step.value}", outcome)

    def _build_compensation_event(
        self, event_name: str, payload: dict[str, Any]
    ) -> OutboxMessage:
        """Build a CloudEvents-compatible compensation message."""
        now = datetime.now(UTC)
        return OutboxMessage(
            event_id=str(ULID()),
            event_name=event_name,
            partition_key=self.trip_id,
            payload=__import__("json").dumps(
                {
                    **payload,
                    "trip_id": self.trip_id,
                    "compensated_at_utc": now.isoformat(),
                },
                default=str,
            ),
            schema_version=1,
            aggregate_type="TRIP",
            aggregate_id=self.trip_id,
        )

    async def start(self) -> None:
        """Initiate the saga by emitting TripCreated event."""
        await self._update_status(SagaStatus.PENDING)
        broker = create_broker(settings.resolved_broker_type)
        try:
            await broker.publish(
                self._build_compensation_event("trip.booking.started.v1", {})
            )
            logger.info("SAGA [%s] started", self.trip_id)
        except Exception:
            logger.exception("SAGA [%s] failed to publish start event", self.trip_id)
            raise
        finally:
            await broker.close()

    async def compensate(self, reason: str) -> None:
        """Trigger compensating actions if a step fails.

        Executes compensation steps sequentially with individual error
        handling so that one failure does not block the remaining steps.
        """
        await self._update_status(SagaStatus.COMPENSATING)
        logger.warning("SAGA [%s] compensating due to: %s", self.trip_id, reason)

        broker = create_broker(settings.resolved_broker_type)
        try:
            # Step 1: Release vehicle reservation via Fleet Service
            try:
                await broker.publish(
                    self._build_compensation_event(
                        "trip.compensate.release_vehicle.v1",
                        {"reason": reason},
                    )
                )
                await self._record_step(_CompensateStep.RELEASE_VEHICLE, "OK")
            except Exception:
                logger.exception(
                    "SAGA [%s] compensation step RELEASE_VEHICLE failed", self.trip_id
                )
                await self._record_step(_CompensateStep.RELEASE_VEHICLE, "ERROR")

            # Step 2: Release driver assignment via Driver Service
            try:
                await broker.publish(
                    self._build_compensation_event(
                        "trip.compensate.release_driver.v1",
                        {"reason": reason},
                    )
                )
                await self._record_step(_CompensateStep.RELEASE_DRIVER, "OK")
            except Exception:
                logger.exception(
                    "SAGA [%s] compensation step RELEASE_DRIVER failed", self.trip_id
                )
                await self._record_step(_CompensateStep.RELEASE_DRIVER, "ERROR")

            # Step 3: Mark trip as FAILED so downstream consumers can reconcile
            try:
                await broker.publish(
                    self._build_compensation_event(
                        "trip.compensate.mark_failed.v1",
                        {"reason": reason},
                    )
                )
                await self._record_step(_CompensateStep.MARK_TRIP_FAILED, "OK")
            except Exception:
                logger.exception(
                    "SAGA [%s] compensation step MARK_TRIP_FAILED failed", self.trip_id
                )
                await self._record_step(_CompensateStep.MARK_TRIP_FAILED, "ERROR")

        finally:
            await broker.close()

        await self._update_status(SagaStatus.FAILED)
        logger.info("SAGA [%s] compensation sequence completed", self.trip_id)
