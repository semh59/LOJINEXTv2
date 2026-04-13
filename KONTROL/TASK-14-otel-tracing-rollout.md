# TASK-14 — OTEL Tracing: driver, fleet, identity, location Servislerine Rollout

## Amaç
Şu an sadece trip-service OpenTelemetry tracing'e sahip. Diğer 4 servise de ekle. Distributed trace Jaeger/Grafana Tempo'da uçtan uca görünsün.

## Kapsam
```
services/driver-service/src/driver_service/tracing.py  (YENİ)
services/driver-service/src/driver_service/main.py
services/fleet-service/src/fleet_service/tracing.py    (YENİ)
services/fleet-service/src/fleet_service/main.py
services/identity-service/src/identity_service/tracing.py  (YENİ)
services/identity-service/src/identity_service/main.py
services/location-service/src/location_service/tracing.py  (YENİ)
services/location-service/src/location_service/main.py
```

## Referans
`services/trip-service/src/trip_service/tracing.py` — bu dosyayı kopyala, namespace güncelle.

## Her servis için tracing.py

Trip-service `tracing.py`'yi kopyala. Sadece import namespace'i değiştir:

```python
# driver için:
from driver_service.config import settings
logger = logging.getLogger("driver_service")
_tracer: trace.Tracer | None = None
# geri kalan trip-service ile aynı
```

## Her servis için main.py güncellemesi

`lifespan` fonksiyonuna ekle:
```python
from {service}.tracing import instrument_app, setup_tracing, shutdown_tracing

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_tracing()           # EKLE
    ...
    try:
        yield
    finally:
        shutdown_tracing()    # EKLE
        ...

def create_app() -> FastAPI:
    app = FastAPI(...)
    instrument_app(app)       # EKLE
    ...
```

## pyproject.toml bağımlılıkları

Her servisin `pyproject.toml`'una ekle (trip-service'de var, diğerlerinde kontrol et):
```toml
"opentelemetry-sdk",
"opentelemetry-exporter-otlp-proto-grpc",
"opentelemetry-instrumentation-fastapi",
"opentelemetry-instrumentation-httpx",
```

## config.py

Her servisin `config.py`'sine ekle:
```python
otel_exporter_otlp_endpoint: str = "http://localhost:4317"
```

## Tamamlanma kriterleri
- [ ] 4 yeni `tracing.py` dosyası oluşturuldu
- [ ] 4 servis main.py'de `setup_tracing()`, `instrument_app()`, `shutdown_tracing()` var
- [ ] pyproject.toml'da OTEL bağımlılıkları var
- [ ] config.py'de `otel_exporter_otlp_endpoint` var
- [ ] Syntax error yok
