import logging
from typing import Any

from platform_common import KafkaConsumerBase

from driver_service.database import async_session_factory

logger = logging.getLogger("driver_service.command_consumer")


class TripCommandConsumer(KafkaConsumerBase):
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
                # driver_id = key
                logger.info("Executing driver reservation command for driver_id=%s", key)
                # handle_driver_reservation_command(session, key, payload)

            await session.commit()
