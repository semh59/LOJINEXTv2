# TASK-15 — Outbox payload_json: Text → JSONB Migration (Tüm Servisler)

## Amaç
Tüm servislerin outbox modellerinde `payload_json` kolonunu `Text`'ten `JSONB`'ye çevir. JSONB ile outbox debug sorguları mümkün olur, GIN index yapılabilir.

## Kapsam
```
services/identity-service/src/identity_service/models.py + alembic
services/fleet-service/src/fleet_service/models.py + alembic
services/location-service/src/location_service/models.py + alembic
services/driver-service/src/driver_service/models.py + alembic
services/trip-service/src/trip_service/models.py + alembic  (TripOutbox için)
```

## Her servis için model değişikliği

```python
# ÖNCE
from sqlalchemy import Text
payload_json: Mapped[str] = mapped_column(Text, nullable=False)

# SONRA
from sqlalchemy.dialects.postgresql import JSONB
from typing import Any
payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

## Her servis için migration

```python
def upgrade() -> None:
    op.alter_column(
        "{servis}_outbox", "payload_json",
        type_=postgresql.JSONB(),
        postgresql_using="payload_json::jsonb"
    )

def downgrade() -> None:
    op.alter_column(
        "{servis}_outbox", "payload_json",
        type_=sa.Text(),
        postgresql_using="payload_json::text"
    )
```

## Relay kodlarında güncelleme

Her servisin outbox relay'inde `json.loads(row.payload_json)` çağrıları kaldırılabilir — JSONB direkt dict döndürür:

```python
# ÖNCE
payload = json.loads(row.payload_json)

# SONRA (JSONB sonrası)
payload = row.payload_json  # zaten dict
```

## Tamamlanma kriterleri
- [ ] 5 servis outbox modeli JSONB kullanıyor
- [ ] 5 migration dosyası mevcut
- [ ] relay kodlarında gereksiz `json.loads` kaldırıldı
- [ ] Syntax error yok
