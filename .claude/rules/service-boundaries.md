# Glob: services/**/*.py

## Service Boundary Rules

These rules are binding. Violating them is a defect, not a style choice.

### Cross-service access
- A service MUST NOT import Python modules from another service's package.
- A service MUST NOT connect to another service's database.
- A service MUST NOT own business logic that belongs to another domain.
- Cross-domain data is exchanged exclusively via HTTP (`httpx.AsyncClient`) or Kafka events.

### ADR-001 (locked)
- Trip calls Fleet for vehicle/trailer reference validation.
- Fleet calls Driver internally.
- Trip MUST NOT call Driver directly.

### Shared packages
- `packages/platform-auth` — JWT validation only. Do not add business logic here.
- `packages/platform-common` — shared utilities. Do not add service-specific logic here.

### Kafka events
- A service may publish events to its own topics.
- A service may consume events from other services' topics.
- Never write directly to another service's database to "sync" data — use events.

### Integration concerns
- Excel exports, Telegram bots, reporting — MUST NOT be absorbed into domain services.
- These belong in separate integration layers or scripts.

### Before adding any cross-service call
1. Check `MEMORY/DECISIONS.md` for existing ADRs.
2. If no ADR covers it, write one before implementing.
