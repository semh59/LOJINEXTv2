# TASK-07 — Fleet Outbox Relay: Double broker.close() Fix

## Amaç
Fleet outbox relay `finally` bloğunda `broker.close()` çağırıyor. Worker entrypoint de `finally` bloğunda `broker.close()` çağırıyor. Double close — Kafka producer ikinci kez flush/close çağrısında exception fırlatır.

## Kapsam
```
services/fleet-service/src/fleet_service/workers/outbox_relay.py
```

## Mevcut sorun
```python
# workers/outbox_relay.py:203 — BU KALDIRILACAK
finally:
    await broker.close()

# entrypoints/worker.py:80 — BU KALACAK (lifecycle yönetimi burada olmalı)
finally:
    await broker.close()
```

## Değişiklik

`workers/outbox_relay.py`'deki `run_outbox_relay` fonksiyonunda `finally` bloğundan `broker.close()` kaldır.

```python
# ÖNCE
async def run_outbox_relay(broker: MessageBroker, ...) -> None:
    try:
        while ...:
            ...
    finally:
        await broker.close()   # KALDIR

# SONRA
async def run_outbox_relay(broker: MessageBroker, ...) -> None:
    while ...:
        ...
    # broker.close() yok — entrypoint yönetir
```

## Doğrulama
```bash
grep -n "broker.close" services/fleet-service/src/fleet_service/workers/outbox_relay.py
# Sonuç boş olmalı
grep -n "broker.close" services/fleet-service/src/fleet_service/entrypoints/worker.py
# Burada olmalı
```

## Tamamlanma kriterleri
- [ ] `workers/outbox_relay.py`'de `broker.close()` yok
- [ ] `entrypoints/worker.py`'de `broker.close()` hâlâ var
