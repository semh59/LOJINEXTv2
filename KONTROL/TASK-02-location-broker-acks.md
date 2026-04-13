# TASK-02 — Broker Durabilite: driver, fleet, location servislerine acks=all ekle

## Amaç
Driver, fleet ve location servislerinin Kafka broker config'ine `acks=all` ve `enable.idempotence=True` ekle. Şu an bu servisler `acks=1` (default) ile çalışıyor — Kafka lider fail olursa event kaybolur, outbox satırı `PUBLISHED` işaretlenmiş olsa bile.

## Kapsam
```
services/driver-service/src/driver_service/broker.py
services/fleet-service/src/fleet_service/broker.py
services/location-service/src/location_service/broker.py
```

## Referans — doğru yapan servis
`services/identity-service/src/identity_service/broker.py:111-112`:
```python
"acks": "all",
"enable.idempotence": True,
```

## Yapılacak değişiklikler

### 1. driver-service/broker.py

`KafkaBroker.__init__` içinde config dict'e ekle:
```python
config: dict[str, object] = {
    "bootstrap.servers": bootstrap_servers,
    "client.id": client_id,
    "acks": "all",                    # EKLE
    "enable.idempotence": True,       # EKLE
}
```

### 2. fleet-service/broker.py

`_kafka_config()` fonksiyonuna ekle:
```python
config: dict[str, str] = {
    "bootstrap.servers": settings.kafka_bootstrap_servers,
    "client.id": settings.kafka_client_id,
    "security.protocol": settings.kafka_security_protocol,
    "acks": "all",                    # EKLE
    "enable.idempotence": "true",     # EKLE (confluent-kafka string kabul eder)
}
```

### 3. location-service/broker.py

`KafkaBroker.__init__` içinde config dict'e ekle:
```python
config: dict[str, Any] = {
    "bootstrap.servers": bootstrap_servers,
    "client.id": client_id,
    "acks": "all",                    # EKLE
    "enable.idempotence": True,       # EKLE
}
```

## Not
`enable.idempotence=True` için Kafka broker'da `max.in.flight.requests.per.connection <= 5` gerekir — Redpanda zaten destekliyor.

## Doğrulama

```bash
python -m compileall services/driver-service/src/driver_service/broker.py
python -m compileall services/fleet-service/src/fleet_service/broker.py
python -m compileall services/location-service/src/location_service/broker.py
python -c "from driver_service.broker import KafkaBroker"
python -c "from fleet_service.broker import KafkaBroker"
python -c "from location_service.broker import KafkaBroker"
```

## Tamamlanma kriterleri
- [ ] driver broker config'de `acks=all` var
- [ ] fleet broker config'de `acks=all` var
- [ ] location broker config'de `acks=all` var
- [ ] Tüm 3 dosyada `enable.idempotence` var
- [ ] Syntax error yok
