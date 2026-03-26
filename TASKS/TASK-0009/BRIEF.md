# TASK-0009: Import/Export API

## Purpose

Finalize the Location Service with high-performance Import (CSV) and memory-efficient streaming Export (CSV) APIs (Section 7.22).

## Requirements

- Asynchronous bulk CSV import with row-level error reporting.
- Memory-efficient streaming CSV export using `StreamingResponse`.
- High-performance database operations (SQLAlchemy Core bulk inserts).
- Strict adherence to V8 spec for CSV field mapping.

## Success Criteria

- [x] Import logic with batch validation.
- [x] Export logic with async generator streaming.
- [x] API endpoints integrated.
- [x] 100% test pass rate for bulk operations.
- [x] Handoff files created according to AGENTS.md.
