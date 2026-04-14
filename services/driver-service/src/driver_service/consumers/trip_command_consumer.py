import logging
from typing import Any

from platform_common import KafkaConsumerBase

from driver_service.database import async_session_factory

logger = logging.getLogger("driver_service.command_consumer")


class TripCommandConsumer(KafkaConsumerBase):  # type: ignore[misc]
    """Consumer for processing commands targeting the Driver bounded context."""

    async def process(
        self,
        topic: str,
        key: str | None,
        payload: dict[str, Any],
        correlation_id: str | None,
        causation_id: str | None,
    ) -> None:
        """Route incoming trip commands locally."""
        event_name = payload.get("event_name", "UNKNOWN")
        logger.info(
            "TripCommandConsumer received command: %s on topic %s (correlation_id=%s)",
            event_name,
            topic,
            correlation_id,
        )

        async with async_session_factory() as session:
            if event_name == "driver.reserve.command":
                driver_id = payload.get("driver_id")
                trip_id = payload.get("trip_id")
                logger.info("Executing driver reservation command for driver_id=%s, trip_id=%s", driver_id, trip_id)

                if driver_id and trip_id:
                    import json

                    from platform_common import utc_now
                    from ulid import ULID

                    from driver_service.models import DriverOutboxModel

                    outbox = DriverOutboxModel(
                        outbox_id=str(ULID()),
                        driver_id=driver_id,
                        aggregate_type="DRIVER",
                        aggregate_id=driver_id,
                        event_name="driver.reserved",
                        payload_json=json.dumps({"trip_id": trip_id, "driver_id": driver_id}),
                        created_at_utc=utc_now(),
                        publish_status="PENDING",
                        correlation_id=correlation_id,
                        causation_id=causation_id,
                    )
                    session.add(outbox)

            await session.commit()
