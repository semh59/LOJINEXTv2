# TASK-18 — Fleet-Service: Kafka Consumer

## Amaç
Fleet-service Kafka consumer yazarak trip event'lerini dinle. `trip.compensate.release_vehicle.v1` ve `trip.completed.v1` event'lerine tepki ver. Bu görev event-driven tam izolasyonun başlangıcı.

## Ön koşul
**TASK-17 tamamlanmış olmalı.**

## Kapsam
```
services/fleet-service/src/fleet_service/consumers/  (YENİ DİZİN)
services/fleet-service/src/fleet_service/consumers/__init__.py
services/fleet-service/src/fleet_service/consumers/trip_events.py
services/fleet-service/src/fleet_service/entrypoints/consumer.py  (YENİ)
services/fleet-service/src/fleet_service/config.py
```

## 1. config.py — consumer ayarları ekle

```python
kafka_consumer_group_id: str = "fleet-service-consumers"
kafka_consumer_topics: list[str] = ["trip.events.v1"]
kafka_consumer_poll_timeout_ms: int = 1000
```

## 2. consumers/trip_events.py

```python
"""Fleet-service handlers for trip domain events."""
from __future__ import annotations
import logging
from typing import Any
from platform_common import parse_envelope, TRIP_COMPLETED_V1, SAGA_COMPENSATE_RELEASE_VEHICLE_V1
from fleet_service.database import async_session_factory

logger = logging.getLogger("fleet_service.consumers.trip_events")


async def handle_trip_event(raw_payload: dict[str, Any]) -> None:
    """Route incoming trip event to the correct handler."""
    try:
        envelope = parse_envelope(raw_payload)
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Failed to parse trip event envelope: %s | raw=%s", exc, raw_payload)
        return

    handlers = {
        TRIP_COMPLETED_V1: _handle_trip_completed,
        SAGA_COMPENSATE_RELEASE_VEHICLE_V1: _handle_release_vehicle,
    }

    handler = handlers.get(envelope.event_name)
    if handler is None:
        logger.debug("No handler for event %s, skipping", envelope.event_name)
        return

    await handler(envelope)


async def _handle_trip_completed(envelope) -> None:
    """Log trip completion — extend for fleet analytics."""
    logger.info(
        "Trip completed: trip_id=%s vehicle_id=%s",
        envelope.aggregate_id,
        envelope.payload.get("vehicle_id"),
    )
    # Gelecek: vehicle utilization tracking, maintenance scheduling


async def _handle_release_vehicle(envelope) -> None:
    """SAGA compensation: release vehicle reservation."""
    vehicle_id = envelope.payload.get("vehicle_id")
    trip_id = envelope.aggregate_id
    logger.warning(
        "SAGA compensation: releasing vehicle %s from trip %s",
        vehicle_id, trip_id,
    )
    # Gelecek: vehicle reservation state güncelle
    # async with async_session_factory() as session:
    #     await release_vehicle_reservation(session, vehicle_id, trip_id)
```

## 3. entrypoints/consumer.py

```python
"""Fleet-service Kafka consumer entrypoint."""
from __future__ import annotations
import asyncio
import json
import logging
import signal
from fleet_service.config import settings
from fleet_service.consumers.trip_events import handle_trip_event
from fleet_service.observability import setup_logging

logger = logging.getLogger("fleet_service.consumer")

try:
    from confluent_kafka.aio import AIOConsumer
except ImportError:
    AIOConsumer = None


async def run_consumer(shutdown_event: asyncio.Event | None = None) -> None:
    if AIOConsumer is None:
        logger.error("confluent-kafka aio not available, consumer cannot start")
        return

    consumer = AIOConsumer({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "group.id": settings.kafka_consumer_group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe(settings.kafka_consumer_topics)
    logger.info("Fleet consumer started, topics=%s", settings.kafka_consumer_topics)

    try:
        while not (shutdown_event and shutdown_event.is_set()):
            msg = await consumer.poll(timeout=settings.kafka_consumer_poll_timeout_ms / 1000)
            if msg is None:
                continue
            if msg.error():
                logger.error("Kafka error: %s", msg.error())
                continue
            try:
                raw = json.loads(msg.value().decode("utf-8"))
                await handle_trip_event(raw)
                consumer.commit(msg)
            except Exception as exc:
                logger.error("Failed to process message: %s", exc)
    finally:
        consumer.close()
        logger.info("Fleet consumer shut down")


def main() -> None:
    setup_logging()
    shutdown_event = asyncio.Event()

    def _stop(sig, frame):
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    asyncio.run(run_consumer(shutdown_event))


if __name__ == "__main__":
    main()
```

## 4. pyproject.toml — entrypoint ekle

```toml
[project.scripts]
fleet-consumer = "fleet_service.entrypoints.consumer:main"
```

## Tamamlanma kriterleri
- [ ] `consumers/` dizini oluşturuldu
- [ ] `trip_events.py` handler'ları var
- [ ] `consumer.py` entrypoint çalışıyor
- [ ] `config.py`'de consumer ayarları var
- [ ] `pyproject.toml`'da entrypoint var
- [ ] Syntax error yok
