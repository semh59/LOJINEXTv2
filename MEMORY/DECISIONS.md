# DECISIONS.md

# Decisions Log

Every significant decision is recorded here:
architecture, technology, direction changes, rejected alternatives.

An agent that does not know a decision was made will make it again — possibly differently.
An agent that does not know why a decision was made may undo it for reasonable-sounding reasons.

---

## How to Write a Decision

```
## [YYYY-MM-DD] Short title

### Context
What situation prompted this decision?

### Decision
What was decided? Be specific.

### Alternatives Considered
What else was evaluated and why was it rejected?

### Consequences
What does this change or constrain going forward?

### Status
active | superseded by [date, title] | reversed on [date]
```

Decisions are never deleted.
If reversed: mark the old one superseded, write a new entry explaining the change.

---

## [YYYY-MM-DD] Agent memory lives in repository files, not in conversation

### Context

Agent sessions have token limits. Conversation context is lost when a session ends.
Agents working on the same project accumulate invisible divergence — each carrying
different mental models built only from their own session history.

### Decision

All project memory lives in files inside the repository.
No agent relies on conversation context as the source of truth.

### Alternatives Considered

- External tools (Notion, Docs): not colocated with code, not visible to automated agents
- System prompt summaries: stale immediately, no reliable update mechanism

### Consequences

Every session starts with a file-reading phase.
In exchange: context loss is eliminated. Any agent can continue any task.

### Status

active

---

## [YYYY-MM-DD] Plan before code is mandatory

### Context

Agents that start coding immediately change scope mid-task, touch wrong files,
or build the wrong thing. A misunderstanding in code costs 10× more to fix than
a misunderstanding in a plan.

### Decision

No code is written until PLAN.md exists and is complete.

### Alternatives Considered

- Plan only for large tasks: rejected — "large" is consistently misjudged
- Skip for quick fixes: rejected — the same failure modes occur at any size

### Consequences

Every task requires a planning step. Scope creep is dramatically reduced.

### Status

active

---

## [2026-03-23] Trip Service technology stack: Python + FastAPI + SQLAlchemy + PostgreSQL

### Context

Trip Service V8 spec is language-agnostic. A technology stack is needed for greenfield implementation.
The spec heavily implies PostgreSQL via `SELECT ... FOR UPDATE SKIP LOCKED`, `TIMESTAMPTZ`, partial unique indexes.

### Decision

- **Runtime:** Python 3.12+
- **Framework:** FastAPI (async ASGI)
- **ORM:** SQLAlchemy 2.0 (async) with Alembic for migrations
- **Database:** PostgreSQL 15+
- **ID generation:** ULID (via `python-ulid`)
- **Async:** `asyncpg` driver
- **Testing:** pytest + httpx.AsyncClient
- **Object storage:** Local filesystem for dev, abstract interface for S3-compatible prod
- **Project location:** `services/trip-service/` within the LOJINEXTv2 repository

### Alternatives Considered

- Go: Higher raw concurrency performance, but slower greenfield development velocity. Spec is compatible.
- Node.js + NestJS: Good if aligning with frontend, but Python is more common for backend-heavy services with complex business logic.
- SQLite: Rejected — spec requires PostgreSQL features (SKIP LOCKED, partial unique indexes, TIMESTAMPTZ)

### Consequences

- All service code lives in `services/trip-service/`
- Python virtual environment management required
- PostgreSQL must be available for development and testing
- Alembic manages schema migrations

### Status

active
