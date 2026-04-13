import logging
from typing import Any

from platform_common import KafkaConsumerBase

from trip_service.database import async_session_factory

# from trip_service.saga_orchestrator import TripSagaCoordinator # To be implemented in Faza 6

logger = logging.getLogger("trip_service.trip_saga_consumer")


class TripSagaEventConsumer(KafkaConsumerBase):
    """Consumer responsible for routing domain events back into the Saga Orchestrator."""

    async def process(
        self,
        topic: str,
        key: str | None,
        payload: dict[str, Any],
        correlation_id: str | None,
        causation_id: str | None,
    ) -> None:
        """Route incoming domain events logically to Saga."""
        event_name = payload.get("event_name", "UNKNOWN")
        logger.info(
            "TripSagaEventConsumer received event: %s on topic %s (correlation_id=%s)",
            event_name,
            topic,
            correlation_id,
        )

        async with async_session_factory() as session:
            from trip_service.saga_orchestrator import TripSagaCoordinator

            coordinator = TripSagaCoordinator(session)
            await coordinator.handle_event(event_name, payload)

            await session.commit()
