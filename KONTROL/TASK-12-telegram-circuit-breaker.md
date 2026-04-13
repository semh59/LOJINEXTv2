# TASK-12 — Telegram Service: HTTP Circuit Breaker

## Amaç
Telegram-service tüm downstream servislere senkron HTTP çağrısı yapıyor, hiçbir resiliency pattern'i yok. Driver, Fleet ve Trip servislerinden herhangi biri down olduğunda Telegram bot tamamen kullanılamaz hale geliyor. Redis-backed circuit breaker ekle.

## Kapsam
```
services/telegram-service/src/telegram_service/http_clients.py
services/telegram-service/src/telegram_service/clients/driver_client.py
services/telegram-service/src/telegram_service/clients/fleet_client.py
services/telegram-service/src/telegram_service/clients/trip_client.py
```

## Yeni dosya: resiliency.py

Trip-service `resiliency.py`'i model alarak oluştur:
```
services/telegram-service/src/telegram_service/resiliency.py
```

İçerik — trip-service `resiliency.py`'yi kopyala, import namespace'i `telegram_service` olarak güncelle:
```python
from telegram_service.observability import get_standard_labels
# CircuitBreaker class aynı kalır

driver_breaker = CircuitBreaker("driver-service")
fleet_breaker = CircuitBreaker("fleet-service")
trip_breaker = CircuitBreaker("trip-service")
```

## client dosyalarına uygula

Her client'ın HTTP metoduna circuit breaker decorator ekle:

```python
# driver_client.py örnek
from telegram_service.resiliency import driver_breaker

@driver_breaker
async def get_driver(driver_id: str) -> dict:
    ...
```

## config.py — Redis URL

`settings.redis_url` mevcut değilse ekle:
```python
redis_url: str = "redis://localhost:6379/0"
```

## Tamamlanma kriterleri
- [ ] `resiliency.py` oluşturuldu
- [ ] `driver_breaker`, `fleet_breaker`, `trip_breaker` tanımlı
- [ ] Her client'ın dış HTTP çağrısına decorator uygulandı
- [ ] `CircuitBreakerError` handler'ı var — graceful error mesajı dönüyor
- [ ] Syntax error yok
