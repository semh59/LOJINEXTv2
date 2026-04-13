# TASK-04 — Location Outbox Relay: Session Açıkken HTTP Yasak

## Amaç
Location `outbox_relay.py`'deki `run_once()` metodu tek bir DB session içinde hem claim hem Kafka publish hem de update yapıyor. Kafka IO sırasında session açık kalıyor — connection pool tükeniyor. Trip-service'in BUG-04 fix pattern'ini uygula.

## Kapsam
```
services/location-service/src/location_service/outbox_relay.py
```

## Mevcut sorun
```python
async def run_once(self) -> int:
    async with async_session_factory() as session:   # session açıldı
        events = await self._claim_batch(session)
        for event in events:
            success = await self._publish_event(event)   # Kafka IO — session hâlâ açık
            await self._update_event_status(session, event, success)
```

## Yapılacak değişiklik

`run_once()` üç aşamaya bölünecek:

```python
async def run_once(self) -> int:
    # Aşama 1: Claim — session açıl, commit, kapat
    async with async_session_factory() as session:
        events = await self._claim_batch(session)
        if not events:
            return 0
    # session kapandı

    # Aşama 2: Publish — session YOK
    results: list[tuple[str, bool]] = []
    for event in events:
        success = await self._publish_event(event)
        results.append((event.outbox_id, success))

    # Aşama 3: Update — yeni session, her satır için re-fetch with FOR UPDATE
    processed = 0
    for outbox_id, success in results:
        await self._finalize_event(outbox_id, success)
        processed += 1

    return processed

async def _finalize_event(self, outbox_id: str, success: bool) -> None:
    """Re-fetch with FOR UPDATE, update status, commit, close."""
    async with async_session_factory() as session:
        row = await session.get(
            LocationOutboxModel, outbox_id,
            options=[with_for_update()]   # sqlalchemy.orm.with_for_update
        )
        if row is None:
            return
        now = datetime.now(UTC)
        if success:
            row.publish_status = "PUBLISHED"
            row.published_at_utc = now
            row.claim_expires_at_utc = None
            row.claim_token = None
            row.claimed_by_worker = None
        else:
            row.attempt_count += 1
            row.claim_expires_at_utc = None
            row.claim_token = None
            row.claimed_by_worker = None
            if row.attempt_count >= settings.outbox_retry_max:
                row.publish_status = "DEAD_LETTER"
            else:
                row.publish_status = "FAILED"
                import random
                base = min(2 ** row.attempt_count * 5, 300)  # 5s base, jitter TASK-05'te
                row.next_attempt_at_utc = now + timedelta(seconds=base)
        await session.commit()
```

`_update_event_status` metodunu kaldır (artık gerekli değil).

## Doğrulama
```bash
python -m compileall services/location-service/src/location_service/outbox_relay.py
grep -n "async with async_session_factory" services/location-service/src/location_service/outbox_relay.py
# run_once() içinde async with OLMAMALI
```

## Tamamlanma kriterleri
- [ ] `run_once()` içinde session yokken `_publish_event` çağrılıyor
- [ ] Her güncelleme yeni session + re-fetch with FOR UPDATE ile yapılıyor
- [ ] `session.merge()` kullanılmıyor
- [ ] Syntax error yok
