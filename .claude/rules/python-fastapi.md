# Glob: services/**/*.py, packages/**/*.py

## Python & FastAPI Standards

### Async
- All route handlers, service methods, and repository calls MUST be `async def`.
- Use `async with session` for all DB operations — never sync sessions.
- Use `httpx.AsyncClient` for all outbound HTTP — never `requests`.

### SQLAlchemy 2.0
- Use `select()`, `update()`, `delete()` from `sqlalchemy` — no legacy `Query` API.
- Always pass `session` explicitly — no global session state.
- Relationships: use `selectinload` or `joinedload` — never implicit lazy loads in async context.

### Pydantic v2
- Use `model_config = ConfigDict(...)` — never inner `class Config`.
- Use `model_validate()` instead of `parse_obj()`.
- Use `model_dump()` instead of `dict()`.

### IDs & Timestamps
- All entity IDs: ULID (26-char string) via `python-ulid` — never UUID.
- All timestamps: `datetime` with UTC timezone — never naive datetime.
- Default ID generation: `default=lambda: str(ULID())` in SQLAlchemy column.

### Error Handling
- Raise `HTTPException` with platform-standard error body (see `PLATFORM_STANDARD.md` §6).
- Never return raw Python exceptions to the client.
- Do not add try/except for scenarios that cannot happen — trust SQLAlchemy and Pydantic contracts.

### Imports
- Group: stdlib → third-party → local packages → service-internal.
- Never use wildcard imports (`from x import *`).
