# Driver Service (V2.1 Spec Compliant)

The Driver Service is responsible for canonical master data management, lifecycle transitions, internal lookup checks, and import workflows for drivers within the LOJINEXT enterprise system.

It implements strict data validations, phone number and turkish name normalizations, and idempotent transitions.

## Features Added in Full Compliance with V2.1 Spec:

- Canonical CRUD and validation endpoints for Driver operations.
- Outbox pattern for publishing up to 8 domain events to Kafka relay.
- Internal eligibility checks tailored for the Trip Service validation pipeline.
- Bulk asynchronous CSV imports.
- Observability layer using Prometheus metrics and structured logging.
- Pydantic models with `If-Match` based ETag concurrency protection.
- Hard delete & Driver Merge logic.

## Key Technical Decisions

- `postgresql_where` is utilized to apply partial unique constraints (phone, telegram_user_id) for ACTIVE/INACTIVE drivers, ignoring SOFT_DELETED ones.
- Strict state machine enforcement: A driver must be moved `SOFT_DELETED` -> `INACTIVE` is forbidden, requires manual restoration to `ACTIVE`.

## Observability

- Exposed `/metrics` endpoint with counters `HTTP_REQUESTS_TOTAL`, `HTTP_REQUEST_DURATION_SECONDS`, `DRIVERS_CREATED_TOTAL`, `DRIVERS_SOFT_DELETED_TOTAL`, `OUTBOX_EVENTS_PUBLISHED`, `OUTBOX_PUBLISH_FAILURES`.
- Full detailed logs are printed out using `StructuredFormatter` into stdout in `JSON` strings allowing Datadog or ELK stack parsers to analyze it automatically.
- Log entries are augmented with HTTP Request IDs for deep tracing across the distributed infrastructure.

## Testing

A full comprehensive matrix containing 54 robust tests is present and verifies:

- `tests/test_normalization.py` - Custom validations and heuristics unit tests.
- `tests/test_crud_endpoints.py` - Core integrity checks, constraint assertions on CREATE, PATCH.
- `tests/test_lifecycle.py` - State machines, audit logger validation, and idempotent transitions.
- `tests/test_internal_endpoints.py` - Eligibility and references integration tests safely tested via async contexts.
- `tests/test_contract.py` - Schema verifications explicitly checking 8 domain events structure parity.
- `tests/test_edge_cases.py` - Concurrency, monkeypatching Trip API reference checks.
- `tests/test_smoke.py` - Deep end-to-end traversal from creating to hard-deleting the same driver safely.

All verified properly to assert total fault-tolerance in production environments!
