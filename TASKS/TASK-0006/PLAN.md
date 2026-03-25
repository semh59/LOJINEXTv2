# TASK-0006: Processing Pipeline Implementation Plan

## Proposed Changes

### 1. Provider Adapters

- [x] `src/location_service/providers/mapbox_directions.py`: Driving/Truck profile.
- [x] `src/location_service/providers/mapbox_terrain.py`: Terrain-RGB tile decoding.
- [x] `src/location_service/providers/ors_validation.py`: HGV profile validation.

### 2. Domain & Hashing

- [x] `src/location_service/domain/hashing.py`: Fix RFC 8785 implementation for dicts.
- [x] `src/location_service/domain/classification.py`: Segment classification logic.

### 3. Processing Pipeline

- [x] `src/location_service/processing/pipeline.py`: Implement the 30-step algorithm with bidirectional support.
- [x] Use `async_session_factory` for atomic transactions.

### 4. API Routers

- [x] `src/location_service/routers/processing.py`: Add `/calculate`, `/refresh`, and status endpoints.
- [x] Register router in `main.py`.

## Verification Strategy

- **Unit Tests**: `tests/test_unit.py` for domain logic (Pass).
- **Contract Tests**: `tests/test_providers.py` for external APIs using mocks (Pass).
- **Integration Tests**: `tests/test_processing_flow.py` for end-to-end trigger lifecycle (Blocked by Docker).
