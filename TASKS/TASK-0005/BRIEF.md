# Location Service API Endpoints (TASK-0005)

Phase 4 of the Location Service Greenfield Implementation.

## Scope

Implement the FastApi contract endpoints (Sections 4.3, 4.10):

1. **routers/points.py**: CRUD for canonical Location Points.
2. **routers/pairs.py**: CRUD and triggers for Route Pairs.
3. **main.py**: App registration.
4. **Contract Tests**: FastApi client integration tests against the Postgres schema.

## Dependencies

Requires the successfully established database schema (TASK-0003) and the pure domain logic (TASK-0004) to serve normalized outputs and apply logic inside future handlers.
