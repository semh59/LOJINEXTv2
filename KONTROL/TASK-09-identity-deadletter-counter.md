# TASK-09 — Identity Dead-Letter Counter: Yanlış Tetikleme Fix

## Amaç
Identity outbox relay dead-letter counter her publish hatasında artıyor. Yalnızca gerçek `DEAD_LETTER` geçişinde artması gerekiyor.

## Kapsam
```
services/identity-service/src/identity_service/workers/outbox_relay.py
```

## Sorun
```python
# satır ~226-232
except Exception as exc:
    await _mark_publish_failure(outbox_id, exc)
    row_data = await _load_claimed_payload(outbox_id)
    if row_data is None:           # her zaman None — _mark_publish_failure status değiştirdi
        OUTBOX_DEAD_LETTER_TOTAL.labels(**labels).inc()   # her hatada artıyor
```

`_load_claimed_payload` `publish_status != "PUBLISHING"` ise `None` döndürüyor. `_mark_publish_failure` status'u değiştiriyor → sonraki `_load_claimed_payload` her zaman `None` → counter her zaman artıyor.

## Düzeltme

`_mark_publish_failure` fonksiyonunu değiştir — `DEAD_LETTER`'a geçip geçmediğini return et:

```python
async def _mark_publish_failure(outbox_id: str, exc: Exception) -> bool:
    """Returns True if row was transitioned to DEAD_LETTER."""
    async with async_session_factory() as session:
        row = await session.get(IdentityOutboxModel, outbox_id)
        if row is None:
            return False
        row.attempt_count += 1
        row.last_error_code = str(exc)[:100]
        row.claim_token = None
        row.claim_expires_at_utc = None
        row.claimed_by_worker = None
        transitioned_to_dl = False
        if row.attempt_count >= settings.outbox_max_retries:
            row.publish_status = "DEAD_LETTER"
            transitioned_to_dl = True
        else:
            row.publish_status = "FAILED"
            # backoff hesapla
            ...
        await session.commit()
        return transitioned_to_dl
```

Caller'da:
```python
except Exception as exc:
    is_dead_letter = await _mark_publish_failure(outbox_id, exc)
    if is_dead_letter:
        OUTBOX_DEAD_LETTER_TOTAL.labels(**labels).inc()
    return False
```

## Tamamlanma kriterleri
- [ ] Dead-letter counter yalnızca `DEAD_LETTER`'a geçişte artıyor
- [ ] Her publish hatasında artmıyor
- [ ] Syntax error yok
