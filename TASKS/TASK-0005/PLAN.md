# Implementation Plan - TASK-0005

## 1. routers/points.py

- Implement Pydantic request/response schemas.
- Dependency inject the async SQLAlchemy session.
- Apply `RequestIdMiddleware` implicitly per app.
- Write endpoints: `POST /v1/points`, `GET /v1/points/{id}`, `GET /v1/points`, `PATCH /v1/points/{id}`.

## 2. routers/pairs.py

- Implement Pydantic request/response schemas.
- Write endpoints: `POST /v1/pairs`, `GET /v1/pairs/{id}`, `GET /v1/pairs`, `PATCH /v1/pairs/{id}`, `POST /v1/pairs/{id}/calculate`.

## 3. tests/test_points_api.py & test_pairs_api.py

- Write exhaustive integration tests simulating HTTP requests against the FastAPI app via `httpx.AsyncClient`.
- Ensure constraints and 4xx/5xx responses are managed properly by the existing `errors.py`.
