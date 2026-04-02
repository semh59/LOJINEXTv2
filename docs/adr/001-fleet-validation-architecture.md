# ADR-001: Fleet Validation Architecture

## Date

2026-04-02

## Status

Accepted

## Context

The Trip service currently validates trips against a non-existent `fleet-api` endpoint `/internal/v1/trip-references/validate`. The architecture initially implied separate trip validation queries to Fleet and Driver entities individually, or an aggregated endpoint within Fleet. A stable and simple approach is needed to handle trip validation (Driver, Vehicle, Trailer) without exposing Trip to partial failures, Driver-vs-Fleet branching logic, or duplicate network hops.

## Decision

We choose **Option 1 (Aggregation Facade)**.

Fleet V1 will preserve the single `/internal/v1/trip-references/validate` endpoint required by the Trip service. Fleet itself will act as an aggregator that internally resolves:

- `driver_id` via internal communication with the Driver service.
- `vehicle_id` and `trailer_id` via Fleet's own database.

In addition:

- The Fleet → Driver internal authentication contract MUST use service JWTs to prevent shared-secret rot.
- The readiness probes will continue to reflect truth: since Fleet is an active runtime dependency for Trip validation, Trip readiness must probe Fleet, establishing explicit dependency on the aggregated validation hook.
- For the current release phase, `fleet-api` is treated as an optional external dependency or heavily mocked at the network layer if a full Fleet deployment is not included in the scope.

## Consequences

- Trip requires merely one network hop to resolve entire resource references before assignment.
- Avoids complex coordination logic in Trip.
- Requires Fleet service to take ownership of talking to the Driver service, which adds inter-service dependencies.
- Establishes a firm requirement for tightly synced internal JWT shared secrets across Trip, Location, Driver, and Fleet.
