# TASK-22 — Trip-Service: Senkron Location HTTP → Graceful Degradation

## Amaç
Trip-service, location-service'e `fetch_trip_context` ve `resolve_route_by_names` için senkron HTTP yapıyor. Location down olursa tüm trip oluşturma durur. Telegram slip flow'u için graceful degradation ekle — context eksikse trip `PENDING_REVIEW` girer, enrichment worker sonradan tamamlar.

## Ön koşul
**TASK-17, TASK-20 tamamlanmış olmalı.**

## Kapsam
```
services/trip-service/src/trip_service/dependencies.py
services/trip-service/src/trip_service/routers/trips.py
```

## Değişiklik: fetch_trip_context — soft failure modu

```python
async def fetch_trip_context(
    pair_id: str,
    *,
    field_name: str = "body.route_pair_id",
    required: bool = True,          # YENİ PARAMETRE
) -> LocationTripContext | None:    # None döndürebilir
    """
    required=True  → mevcut davranış, hata fırlatır (ADMIN_MANUAL)
    required=False → location down olursa None döner (TELEGRAM_TRIP_SLIP)
    """
    try:
        response = await _location_context_raw(pair_id)
    except CircuitBreakerError as exc:
        if not required:
            logger.warning("Location unavailable (soft mode), skipping context: %s", exc)
            return None
        raise trip_dependency_unavailable(...) from exc
    except httpx.HTTPError as exc:
        if not required:
            logger.warning("Location HTTP error (soft mode): %s", exc)
            return None
        raise trip_dependency_unavailable(...) from exc

    # ... mevcut response parsing
```

## Telegram slip ingest — soft mode kullan

```python
# routers/trips.py — ingest_trip_slip
context = await fetch_trip_context(
    resolution.pair_id,
    field_name="body.origin_name",
    required=False,   # location down olsa da ingest devam eder
)
if context is not None:
    apply_trip_context(trip, context, reverse=False)
# context None ise: enrichment worker sonradan tamamlar
```

## Admin manual — hard mode (değişmez)

```python
# service.py — create_trip
context = await fetch_trip_context(body.route_pair_id)  # required=True default
```

## Tamamlanma kriterleri
- [ ] `fetch_trip_context` `required` parametresi alıyor
- [ ] Telegram slip için location down → trip PENDING_REVIEW giriyor, 503 yok
- [ ] Admin manual için location down → 503 (değişmedi)
- [ ] `required=True` default — mevcut çağrılar bozulmuyor
- [ ] Syntax error yok
