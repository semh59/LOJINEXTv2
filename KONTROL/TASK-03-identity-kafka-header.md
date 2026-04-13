# TASK-03 — Identity Broker: Kafka Header Casing Düzeltme

## Amaç
Identity-service Kafka mesajlarına `x-correlation-id` (lowercase) header ekliyor. Diğer tüm servisler `X-Correlation-ID` kullanıyor. Case-sensitive consumer'lar identity event'lerinde correlation context bulamaz.

## Kapsam
```
services/identity-service/src/identity_service/broker.py
```

## Değişiklik
Satır 123:
```python
# ÖNCE
headers.append(("x-correlation-id", c_id.encode()))

# SONRA
headers.append(("X-Correlation-ID", c_id.encode()))
```

## Doğrulama
```bash
grep -n "Correlation" services/identity-service/src/identity_service/broker.py
# Çıktı: X-Correlation-ID (büyük harf) olmalı
```

## Tamamlanma kriterleri
- [ ] `broker.py`'de `X-Correlation-ID` (büyük harf) var
- [ ] `x-correlation-id` (küçük harf) yok
