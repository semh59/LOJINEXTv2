# Location Service Domain Logic (TASK-0004)

Phase 3 of the Location Service Greenfield Implementation.

## Scope

Implement the pure Python domain logic layer (no DB dependencies, no FastApi dependencies):

1. **TR/EN Normalization** (Section 5.1): Dotless-i handling, NFKC, uppercase, trim, collapse.
2. **Code Generation** (Section 5.2 & 5.3): `pair_code` (ULID) and `route_code`.
3. **Classification** (Section 5.4, 5.5, 5.6): Grade thresholds, speed bands (kph/mph), road class mappings.
4. **Hashing** (Section 16 & 6.8): `draft_set_hash` (RFC 8785 strict) and `field_origin_matrix_hash`.
5. **JSON Distributions** (Section 6.7): Road type, speed, urban percentage derivations.

## Mandatory Tests

Per Section 22:

- Unit tests for TR/EN normalization (divergence on `ISTANBUL`).
- Unit tests for Grade formula and 5 class thresholds.
- Unit tests for Road-class mapping.
- Unit tests for Speed band logic.
- Unit tests for RFC 8785 hashing with numeric precision.
