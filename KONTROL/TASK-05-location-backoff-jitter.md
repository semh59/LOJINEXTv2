# TASK-05 — Location Outbox Backoff: Jitter + Base Delay Standardizasyon

## Amaç
Location outbox relay backoff'u platform standardına getir: base delay 5s, ±10% jitter, max 300s.

## Kapsam
```
services/location-service/src/location_service/outbox_relay.py
```

## Mevcut sorun
```python
backoff = min(2**event.attempt_count, 300)  # base 1s, jitter yok
```

## Referans — trip-service standardı
```python
OUTBOX_BACKOFF_SECONDS = [5, 10, 30, 60, 300]
jitter = delay * 0.1
actual_delay = delay + random.uniform(-jitter, jitter)
```

## Değişiklik

Dosyanın üstüne sabitleri ekle:
```python
import random
_BACKOFF_SCHEDULE = [5, 10, 30, 60, 300]  # saniye

def _compute_backoff(attempt_count: int) -> float:
    idx = min(max(attempt_count - 1, 0), len(_BACKOFF_SCHEDULE) - 1)
    base = _BACKOFF_SCHEDULE[idx]
    jitter = base * 0.1
    return max(1.0, base + random.uniform(-jitter, jitter))
```

Backoff hesaplama satırını değiştir:
```python
# ÖNCE
backoff = min(2**event.attempt_count, 300)
event.next_attempt_at_utc = now + timedelta(seconds=backoff)

# SONRA
event.next_attempt_at_utc = now + timedelta(seconds=_compute_backoff(event.attempt_count))
```

## Tamamlanma kriterleri
- [ ] `_compute_backoff` fonksiyonu var
- [ ] İlk backoff 5 saniye civarı (±10%)
- [ ] Jitter uygulanıyor
- [ ] `2**attempt_count` formülü yok
