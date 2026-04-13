# TASK-21 — Trip-Service: Senkron Fleet HTTP → Event-Driven

## Amaç
Trip-service şu an trip oluşturma sırasında Fleet-service'e senkron HTTP yaparak driver/vehicle/trailer referanslarını doğruluyor. Fleet-service down olduğunda tüm trip oluşturma 503 dönüyor. Bu bağımlılığı kaldır — validation'ı event-driven yapıya taşı.

## Ön koşul
**TASK-17, TASK-18 tamamlanmış olmalı.**

## Strateji

"Validation-at-review" yaklaşımı: Telegram slip ve Excel import kaynaklı tripler zaten `PENDING_REVIEW` statüsüne giriyor. Bu source_type'lar için fleet validation zorunlu değil — reviewer onay sırasında kontrol eder. Manuel oluşturma için ise fleet up olduğunda validate, down olduğunda graceful fallback.

## Kapsam
```
services/trip-service/src/trip_service/dependencies.py
services/trip-service/src/trip_service/service.py
services/trip-service/src/trip_service/routers/trips.py
```

## Değişiklik 1: ensure_trip_references_valid — source_type'a göre soft/hard

```python
async def ensure_trip_references_valid(
    *,
    driver_id: str | None,
    vehicle_id: str | None,
    trailer_id: str | None,
    source_type: str = "ADMIN_MANUAL",
    field_prefix: str = "body",
) -> None:
    """
    Hard validation: ADMIN_MANUAL, EMPTY_RETURN_ADMIN, EXCEL_IMPORT
    Soft validation: TELEGRAM_TRIP_SLIP (down olursa devam et, PENDING_REVIEW'da çözülür)
    """
    soft_sources = {"TELEGRAM_TRIP_SLIP"}
    
    try:
        result = await validate_trip_references(
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            trailer_id=trailer_id,
        )
    except (CircuitBreakerError, httpx.HTTPError) as exc:
        if source_type in soft_sources:
            logger.warning(
                "Fleet validation unavailable for %s source — continuing with PENDING_REVIEW: %s",
                source_type, exc,
            )
            return  # Soft: devam et
        raise trip_dependency_unavailable(
            "Fleet Service validation is unavailable."
        ) from exc

    # Validation sonuçlarını işle (mevcut kod kalır)
    ...
```

## Değişiklik 2: service.py ve routers/trips.py — source_type geçir

`ensure_trip_references_valid` çağrılarına `source_type` parametresi ekle:

```python
# service.py — create_trip
await ensure_trip_references_valid(
    driver_id=body.driver_id,
    vehicle_id=body.vehicle_id,
    trailer_id=body.trailer_id,
    source_type=SourceType.ADMIN_MANUAL,
)

# routers/trips.py — ingest_trip_slip
await ensure_trip_references_valid(
    driver_id=body.driver_id,
    vehicle_id=body.vehicle_id,
    trailer_id=body.trailer_id,
    source_type=SourceType.TELEGRAM_TRIP_SLIP,   # soft
)
```

## Tamamlanma kriterleri
- [ ] `ensure_trip_references_valid` `source_type` parametresi alıyor
- [ ] Telegram slip için fleet down olduğunda 503 değil devam ediyor
- [ ] Admin manual için fleet down olduğunda 503 dönüyor
- [ ] Mevcut testler geçiyor
- [ ] Syntax error yok
