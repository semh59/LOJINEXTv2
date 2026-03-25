# TASK-0006: Location Service — Provider Adapters & Processing Pipeline

## Current Status

**Status:** in-progress
**Phase:** Phase 5 — Provider Adapters & Processing Pipeline

## Context

Implementing the bidirectional normative processing pipeline for the Location Service. This includes integration with Mapbox Directions and Terrain APIs, ORS for validation, and a 30-step atomic calculation algorithm.

## Objectives

- Implement Mapbox Directions client with truck profiles.
- Implement Mapbox Terrain-RGB client for elevation enrichment.
- Implement OpenRouteService validation client with graceful degradation.
- Implement the 30-step normative algorithm in `processing/pipeline.py`.
- Ensure bidirectional (Forward/Reverse) route processing in a single atomic transaction.
- Create REST API endpoints for calculation trigger and monitoring.

## Success Criteria

- [ ] Mapbox and ORS adapters pass contract tests.
- [ ] Bidirectional routes are calculated and stored in a single transaction.
- [ ] Elevation data is correctly enriched from Terrain-RGB tiles.
- [ ] Routes are validated against ORS with a 20% distance threshold.
- [ ] Integration test `tests/test_processing_flow.py` passes.
