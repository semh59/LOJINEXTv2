# TASK-19 — Driver-Service: Kafka Consumer

## Amaç
Driver-service Kafka consumer yazarak trip event'lerini dinle. `trip.compensate.release_driver.v1` SAGA compensation event'ini işle.

## Ön koşul
**TASK-17 tamamlanmış olmalı. TASK-18 tamamlandıysa pattern'i referans al.**

## Kapsam
```
services/driver-service/src/driver_service/consumers/
services/driver-service/src/driver_service/consumers/__init__.py
services/driver-service/src/driver_service/consumers/trip_events.py
services/driver-service/src/driver_service/entrypoints/consumer.py  (YENİ)
services/driver-service/src/driver_service/config.py
```

## TASK-18 ile aynı pattern — sadece namespace ve handler'lar farklı

### config.py
```python
kafka_consumer_group_id: str = "driver-service-consumers"
kafka_consumer_topics: list[str] = ["trip.events.v1"]
kafka_consumer_poll_timeout_ms: int = 1000
```

### consumers/trip_events.py

```python
from platform_common import parse_envelope, TRIP_COMPLETED_V1, SAGA_COMPENSATE_RELEASE_DRIVER_V1

async def handle_trip_event(raw_payload: dict) -> None:
    envelope = parse_envelope(raw_payload)
    handlers = {
        TRIP_COMPLETED_V1: _handle_trip_completed,
        SAGA_COMPENSATE_RELEASE_DRIVER_V1: _handle_release_driver,
    }
    handler = handlers.get(envelope.event_name)
    if handler:
        await handler(envelope)


async def _handle_trip_completed(envelope) -> None:
    """Trip tamamlandı — sürücü müsaitlik durumu güncellenebilir."""
    logger.info(
        "Trip completed: trip_id=%s driver_id=%s",
        envelope.aggregate_id,
        envelope.payload.get("driver_id"),
    )


async def _handle_release_driver(envelope) -> None:
    """SAGA compensation: sürücü atamasını serbest bırak."""
    driver_id = envelope.payload.get("driver_id")
    trip_id = envelope.aggregate_id
    logger.warning(
        "SAGA compensation: releasing driver %s from trip %s",
        driver_id, trip_id,
    )
```

### entrypoints/consumer.py
TASK-18'deki `consumer.py` ile aynı — sadece import namespace'i `driver_service` olarak güncelle.

### pyproject.toml
```toml
[project.scripts]
driver-consumer = "driver_service.entrypoints.consumer:main"
```

## Tamamlanma kriterleri
- [ ] `consumers/trip_events.py` var
- [ ] `entrypoints/consumer.py` var
- [ ] `SAGA_COMPENSATE_RELEASE_DRIVER_V1` handler'ı var
- [ ] `config.py`'de consumer ayarları var
- [ ] Syntax error yok
