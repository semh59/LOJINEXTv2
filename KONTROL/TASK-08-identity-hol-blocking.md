# TASK-08 — Identity Outbox Relay: HOL Blocking Düzeltme

## Amaç
TASK-01 tamamlandıktan sonra çalıştır. Identity outbox relay HOL blocking subquery'si `partition_key` kolonunu referans alıyor. TASK-01 kolonu ekledi, bu görev relay'in bu kolonu doğru kullandığını doğrular ve gerekirse düzeltir.

## Ön koşul
**TASK-01 tamamlanmış olmalı.**

## Kapsam
```
services/identity-service/src/identity_service/workers/outbox_relay.py
```

## Mevcut durum (TASK-01 sonrası)
```python
o2 = aliased(IdentityOutboxModel)
hol_subq = select(1).where(
    o2.partition_key == IdentityOutboxModel.partition_key,
    o2.publish_status != "PUBLISHED",
    o2.created_at_utc < IdentityOutboxModel.created_at_utc,
)
```

Bu kod TASK-01 sonrası çalışacak. Ama outbox satırları yazılırken `partition_key` set edilmeli.

## Kontrol edilecekler

### 1. Outbox satırı yazılırken partition_key set ediliyor mu?

`token_service.py` veya outbox insert yapılan yerde:
```python
outbox_row = IdentityOutboxModel(
    ...
    partition_key=aggregate_id,   # set edilmeli
    correlation_id=correlation_id.get(),
)
```

Set edilmiyorsa ekle.

### 2. HOL blocking subquery doğru çalışıyor mu?

Subquery'nin `NOT EXISTS` ile kullanıldığını doğrula:
```python
.where(not_(hol_subq.exists()))
```

### 3. `aggregate_id` partition olarak mantıklı mı?

Identity için `aggregate_id = user_id`. Aynı kullanıcı için eventler sıralı işlenmeli. Bu doğru.

## Test
```python
from identity_service.models import IdentityOutboxModel
row = IdentityOutboxModel()
row.partition_key = "test"  # AttributeError olmamalı
print("OK")
```

## Tamamlanma kriterleri
- [ ] Outbox insert'te `partition_key=aggregate_id` set ediliyor
- [ ] `correlation_id` insert'te set ediliyor
- [ ] HOL blocking query syntax error yok
- [ ] `python -c "from identity_service.models import IdentityOutboxModel; IdentityOutboxModel().partition_key"` hata vermiyor
