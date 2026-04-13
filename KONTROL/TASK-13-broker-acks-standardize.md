# TASK-13 — Broker Config Standardizasyon: Tüm Servisler

## Amaç
Tüm servislerin broker config'ini trip-service standardına getir: configurable settings, linger_ms, batch_size, compression.

## Kapsam
```
services/driver-service/src/driver_service/config.py
services/driver-service/src/driver_service/broker.py
services/fleet-service/src/fleet_service/config.py
services/fleet-service/src/fleet_service/broker.py
services/location-service/src/location_service/config.py
services/location-service/src/location_service/broker.py
```

## Referans — trip-service config.py
```python
kafka_acks: str = "all"
kafka_enable_idempotence: bool = True
kafka_linger_ms: int = 5
kafka_batch_size: int = 32768
kafka_compression_type: str = "lz4"
```

## Her servis için yapılacak

### 1. config.py'ye ekle (env prefix servis adıyla)
```python
# driver için DRIVER_ prefix
kafka_acks: str = "all"
kafka_enable_idempotence: bool = True
kafka_linger_ms: int = 5
kafka_batch_size: int = 32768
kafka_compression_type: str = "lz4"
```

### 2. broker.py'de kullan
```python
config = {
    "bootstrap.servers": ...,
    "client.id": ...,
    "acks": settings.kafka_acks,
    "enable.idempotence": settings.kafka_enable_idempotence,
    "linger.ms": settings.kafka_linger_ms,
    "batch.size": settings.kafka_batch_size,
    "compression.type": settings.kafka_compression_type,
}
```

## Tamamlanma kriterleri
- [ ] driver-service config'de kafka_acks var
- [ ] fleet-service config'de kafka_acks var
- [ ] location-service config'de kafka_acks var
- [ ] Tüm 3 serviste broker config settings'ten okuyor
- [ ] Syntax error yok
