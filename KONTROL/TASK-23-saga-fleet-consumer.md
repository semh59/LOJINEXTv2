# TASK-23 — Fleet-Service: SAGA Compensation Consumer Aktivasyonu

## Amaç
TASK-18'de yazılan `_handle_release_vehicle` handler'ını gerçek iş mantığıyla doldur. Fleet-service artık `trip.compensate.release_vehicle.v1` event'ini alınca araç rezervasyonunu serbest bırakabilmeli.

## Ön koşul
**TASK-18 tamamlanmış olmalı. Fleet-service'te vehicle reservation kavramı incelenmeli.**

## Kapsam
```
services/fleet-service/src/fleet_service/consumers/trip_events.py
services/fleet-service/src/fleet_service/services/vehicle_service.py  (varsa)
```

## Yapılacak

Fleet-service'te araçların "aktif trip" ile ilişkisini tutan bir yapı varsa (trip_id FK veya status alanı), compensation handler bunu temizlemeli:

```python
async def _handle_release_vehicle(envelope) -> None:
    vehicle_id = envelope.payload.get("vehicle_id")
    trip_id = envelope.aggregate_id
    
    if not vehicle_id:
        logger.warning("release_vehicle event missing vehicle_id, skipping")
        return

    async with async_session_factory() as session:
        # Fleet-service modelini incele — active_trip_id veya benzeri alan var mı?
        # Varsa: vehicle.active_trip_id = None, vehicle.status = AVAILABLE
        # Yoksa: sadece audit log yaz
        
        # Outbox event üret: vehicle.released.v1
        outbox_row = FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type="VEHICLE",
            aggregate_id=vehicle_id,
            event_name="vehicle.released.v1",
            event_version=1,
            payload_json=json.dumps({
                "vehicle_id": vehicle_id,
                "released_from_trip": trip_id,
                "reason": "SAGA_COMPENSATION",
            }),
            publish_status="PENDING",
            ...
        )
        session.add(outbox_row)
        await session.commit()
    
    logger.info("Vehicle %s released from trip %s via SAGA compensation", vehicle_id, trip_id)
```

## Fleet model kontrolü

Fleet-service'in mevcut vehicle modelini incele — trip ile bağlantı var mı? Varsa `vehicle_service.py`'ye `release_vehicle_from_trip(session, vehicle_id, trip_id)` metodu ekle.

## Tamamlanma kriterleri
- [ ] `_handle_release_vehicle` gerçek DB işlemi yapıyor
- [ ] Compensation sonrası outbox event üretiyor
- [ ] `vehicle_id` eksikse graceful skip
- [ ] Syntax error yok
