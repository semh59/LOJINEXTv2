# TASK-01 — Identity Outbox Model: Eksik Kolonlar + Migration

## Amaç
`IdentityOutboxModel`'e `partition_key`, `correlation_id`, `causation_id` kolonlarını ekle ve Alembic migration yaz. Şu an `outbox_relay.py:93` var olmayan `partition_key`'i referans alıyor — bu **runtime AttributeError**'dır.

## Kapsam
```
services/identity-service/src/identity_service/models.py
services/identity-service/alembic/versions/<yeni_migration>.py
```

## Mevcut durum
`IdentityOutboxModel` şu kolonlara sahip **değil**:
- `partition_key`
- `correlation_id`  
- `causation_id`

`outbox_relay.py:93` şunu çalıştırıyor:
```python
o2.partition_key == IdentityOutboxModel.partition_key  # AttributeError
```

## Yapılacak değişiklikler

### 1. models.py — IdentityOutboxModel'e eklenecek kolonlar

`published_at_utc` kolonundan **sonra** şunları ekle:

```python
partition_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
causation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

`__table_args__` içine index ekle:
```python
Index("ix_identity_outbox_partition_status", "partition_key", "publish_status", "created_at_utc"),
```

### 2. Alembic migration yaz

Yeni dosya: `alembic/versions/<ulid>_identity_outbox_add_partition_correlation.py`

```python
def upgrade() -> None:
    op.add_column("identity_outbox", sa.Column("partition_key", sa.String(100), nullable=True))
    op.add_column("identity_outbox", sa.Column("correlation_id", sa.String(64), nullable=True))
    op.add_column("identity_outbox", sa.Column("causation_id", sa.String(64), nullable=True))
    op.create_index("ix_identity_outbox_partition_status",
                    "identity_outbox", ["partition_key", "publish_status", "created_at_utc"])
    # Mevcut satırlar için partition_key = aggregate_id backfill
    op.execute("UPDATE identity_outbox SET partition_key = aggregate_id WHERE partition_key IS NULL")

def downgrade() -> None:
    op.drop_index("ix_identity_outbox_partition_status", "identity_outbox")
    op.drop_column("identity_outbox", "causation_id")
    op.drop_column("identity_outbox", "correlation_id")
    op.drop_column("identity_outbox", "partition_key")
```

### 3. outbox_relay.py — partition_key populate

`_publish_single` veya satır oluşturan yerde `partition_key = aggregate_id` set edildiğini kontrol et. Yoksa ekle.

## Doğrulama

```bash
cd services/identity-service
python -m compileall src/identity_service/models.py
python -c "from identity_service.models import IdentityOutboxModel; print(IdentityOutboxModel.partition_key)"
alembic upgrade head  # DB bağlantısı varsa
```

## Tamamlanma kriterleri
- [ ] `IdentityOutboxModel.partition_key` erişilebilir
- [ ] `IdentityOutboxModel.correlation_id` erişilebilir
- [ ] `IdentityOutboxModel.causation_id` erişilebilir
- [ ] Migration dosyası var ve `upgrade/downgrade` içeriyor
- [ ] Syntax error yok
