# Implementation Plan - TASK-0004

## 1. domain/normalization.py

Implement `normalize_tr(text: str) -> str` and `normalize_en(text: str) -> str`.
Use simple replacements for dotted/dotless I/i rules before standard upper casing in TR, and standard NFKC in EN. Remove punctuation using regex and collapse whitespace.

## 2. domain/codes.py

Implement `generate_pair_code() -> str` (`RP_<ULID>`) and `generate_route_code(pair_code, direction)`.

## 3. domain/classification.py

Implement formulas directly from the spec:

- `calculate_grade(start, end, distance) -> grade_pct`
- `assign_grade_class(grade_pct)`
- `map_road_class(mapbox_class)`
- `assign_speed_band(speed_limit, unit)`

## 4. domain/hashing.py

Implement `canonicaljson` / `json.dumps(separators=(',', ':'))` wrapper for `draft_set_hash`.
Implement robust float-to-string format exactly as specified (format strings avoiding exponents, strict 6dp or 4dp output before hashing).

## 5. domain/distributions.py

Iterate segments and group by road_class, speed_limit, and urban. Return percentage distributions matching the JSON spec.

## 6. tests/test_unit.py

Implement all the Section 22 unit tests applicable to Phase 3.
