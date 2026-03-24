# Weather Service Removal Plan

**Objective:** Cleanly remove all weather-related logic, models, schemas, background tasks, and API validations from the Trip Service without breaking existing core functionality.

## 1. Domain & Enums (`src/trip_service/enums.py`)

- Remove `WeatherStatus` enum completely.

## 2. Models & Database (`src/trip_service/models.py`)

- Remove `weather_status` column from `trip_trip_enrichment` table.
- Eliminate index `ix_enrichment_weather`.

## 3. Configuration (`src/trip_service/config.py`)

- Remove `weather_service_url` setting.

## 4. Schemas (`src/trip_service/schemas.py`)

- Remove `weather_status` from `EnrichmentSummary`.
- Remove `skip_weather_enrichment` from `ManualCreateRequest` and `IngestSlipRequest`.

## 5. Background Workers (`src/trip_service/workers/enrichment_worker.py` & `import_worker.py` & `export_worker.py`)

- Remove `_fetch_weather` function and its HTTP requests.
- Remove weather logic from `_derive_final_enrichment_status`.
- Remove `WeatherStatus` checks and fallbacks in `import_worker.py` and `export_worker.py`.

## 6. API Routing (`src/trip_service/routers/trips.py`)

- Remove `weather_status` initializations (`PENDING`).
- Remove `weather_required_for_completion` check from trip completion workflows.
- Remove `skip_weather_enrichment` handling during trip creation/ingestion.

## 7. Setup Database Migrations

- Generate a new Alembic migration: `alembic revision --autogenerate -m "remove_weather"`.
- Verify the auto-generated migration correctly drops the column and index.

## 8. Tests (`tests/`)

- Update mock fixtures and endpoints that simulate weather external service.
- Remove test permutations focusing solely on weather (e.g., "weather skipped", "weather failed").

## 9. Verification

- Run `pytest tests/` locally to ensure the test suite is green.
- Run `ruff` and `mypy` to ensure no dangling imports or type mismatch.
