# TASK-11 — Trip Service: Lokal DQF Wrapper Kaldır

## Amaç
`trip_helpers.py`'deki `_compute_data_quality_flag` wrapper fonksiyonunu kaldır. Router doğrudan `platform_common` versiyonunu kullansın.

## Kapsam
```
services/trip-service/src/trip_service/trip_helpers.py
services/trip-service/src/trip_service/routers/trips.py
```

## Değişiklik 1: trip_helpers.py

Satır 689'daki wrapper fonksiyonu **kaldır**:
```python
# KALDIR — bu fonksiyon sadece platform_common'u çağırıyor
def _compute_data_quality_flag(source_type: str, ocr_confidence: float | None, route_resolved: bool) -> str:
    """Compute the trip data-quality flag using the locked source contract."""
    return compute_data_quality_flag(source_type, ocr_confidence, route_resolved)
```

## Değişiklik 2: routers/trips.py

Import'u güncelle:
```python
# ÖNCE
from trip_service.trip_helpers import (
    _compute_data_quality_flag,
    ...
)

# SONRA — platform_common'dan direkt al
from platform_common import compute_data_quality_flag
```

Kullanım satırını güncelle:
```python
# ÖNCE
data_quality_flag=_compute_data_quality_flag(...)

# SONRA
data_quality_flag=compute_data_quality_flag(...)
```

## Doğrulama
```bash
grep -rn "_compute_data_quality_flag" services/trip-service/src/
# Sonuç boş olmalı
grep -rn "compute_data_quality_flag" services/trip-service/src/
# Sadece platform_common import ve kullanımları olmalı
```

## Tamamlanma kriterleri
- [ ] `_compute_data_quality_flag` wrapper yok
- [ ] Router `platform_common.compute_data_quality_flag` kullanıyor
- [ ] Syntax error yok
