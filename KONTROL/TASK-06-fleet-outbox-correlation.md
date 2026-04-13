# TASK-06 — Fleet Outbox Model: correlation_id Kolonu + Migration

## Amaç
`FleetOutbox` modeline `correlation_id` ekle. Şu an outbox relay `correlation_id.set(outbox_id)` kullanıyor — Kafka header'ında orijinal request correlation ID yerine outbox ID gönderiliyor.

## Kapsam
```
services/fleet-service/src/fleet_service/models.py
services/fleet-service/src/fleet_service/workers/outbox_relay.py
services/fleet-service/alembic/versions/<yeni_migration>.py
```

## Değişiklik

### 1. models.py — FleetOutbox'a kolon ekle

`FleetOutbox` class'ında `causation_id`'nin yanına:
```python
correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

### 2. alembic migration

```python
def upgrade() -> None:
    op.add_column("fleet_outbox",
        sa.Column("correlation_id", sa.String(64), nullable=True))

def downgrade() -> None:
    op.drop_column("fleet_outbox", "correlation_id")
```

### 3. outbox_relay.py — outbox satırı yazılırken correlation_id populate et

Outbox row oluşturulan yerde `correlation_id` set et:
```python
from fleet_service.observability import correlation_id as _correlation_id_var

# outbox row oluştururken:
outbox_row.correlation_id = _correlation_id_var.get()
```

### 4. outbox_relay.py — Kafka header için correlation_id kullan

```python
# ÖNCE (outbox_relay.py:102)
token = correlation_id.set(outbox_id)   # outbox_id yanlış

# SONRA
cid = row.correlation_id or outbox_id
token = correlation_id.set(cid)
```

## Tamamlanma kriterleri
- [ ] `FleetOutbox.correlation_id` kolonu var
- [ ] Migration dosyası mevcut
- [ ] Outbox satırı oluşturulurken correlation_id set ediliyor
- [ ] Relay Kafka header'ında gerçek correlation_id kullanıyor
