# TASK-20 — Location-Service: Kafka Consumer

## Amaç
Location-service Kafka consumer yazarak trip event'lerini dinle. Trip oluşturulduğunda route context event'ini üret — bu event trip-service'in senkron HTTP çağrısını TASK-22'de kaldırmasına zemin hazırlar.

## Ön koşul
**TASK-17 tamamlanmış olmalı.**

## Kapsam
```
services/location-service/src/location_service/consumers/
services/location-service/src/location_service/consumers/__init__.py
services/location-service/src/location_service/consumers/trip_events.py
services/location-service/src/location_service/entrypoints/consumer.py  (YENİ)
services/location-service/src/location_service/config.py
```

### config.py
```python
kafka_consumer_group_id: str = "location-service-consumers"
kafka_consumer_topics: list[str] = ["trip.events.v1"]
kafka_consumer_poll_timeout_ms: int = 1000
```

### consumers/trip_events.py

```python
from platform_common import parse_envelope, TRIP_CREATED_V1, ROUTE_RESOLVED_V1

async def handle_trip_event(raw_payload: dict) -> None:
    envelope = parse_envelope(raw_payload)
    handlers = {
        TRIP_CREATED_V1: _handle_trip_created,
    }
    handler = handlers.get(envelope.event_name)
    if handler:
        await handler(envelope)


async def _handle_trip_created(envelope) -> None:
    """
    Trip oluşturuldu — route pair context doğrula.
    Gelecekte: route_context.ready.v1 event'i üret.
    
    NOT: Bu handler şu an sadece loglama yapıyor.
    TASK-22 tamamlandığında trip-service'in senkron HTTP çağrısı
    bu event akışıyla değiştirilecek.
    """
    route_pair_id = envelope.payload.get("route_pair_id")
    trip_id = envelope.aggregate_id
    
    if not route_pair_id:
        logger.debug("Trip %s has no route_pair_id yet, skipping", trip_id)
        return

    logger.info(
        "Trip created event received: trip_id=%s route_pair_id=%s",
        trip_id, route_pair_id,
    )
    # Gelecek (TASK-22 sonrası):
    # context = await get_route_pair_context(route_pair_id)
    # await publish_outbox_event("route_context.ready.v1", context)
```

### entrypoints/consumer.py
TASK-18 pattern'i, namespace `location_service`.

### pyproject.toml
```toml
location-consumer = "location_service.entrypoints.consumer:main"
```

## Tamamlanma kriterleri
- [ ] `consumers/trip_events.py` var
- [ ] `TRIP_CREATED_V1` handler var
- [ ] `entrypoints/consumer.py` var
- [ ] Syntax error yok
