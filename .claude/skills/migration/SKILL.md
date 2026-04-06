---
name: migration
description: Create and apply Alembic database migrations for LOJINEXTv2 services. Use when the user asks to create a migration, add a column, alter a table, or run migrations. Triggers include "create migration", "add column", "alembic revision", "run migrations", "migrate".
allowed-tools: Bash, Read, Edit
---

# Alembic Migration Skill

## Rules

- Each service has its own independent Alembic migration chain — NEVER share chains across services.
- Migrations run against the service's own database only.
- Never edit an already-applied migration — always create a new one.
- All new columns with defaults should be `NULLABLE` first, then backfilled, then set `NOT NULL` in a separate migration if needed.

## Create a New Migration

```bash
cd services/<service-name>
alembic revision --autogenerate -m "<short description>"
```

Then review the generated file in `alembic/versions/`. Verify:
- `upgrade()` does what you expect
- `downgrade()` correctly reverses it
- No accidental drops of existing columns

## Apply Migrations

```bash
cd services/<service-name>
alembic upgrade head
```

## Check Current State

```bash
cd services/<service-name>
alembic current        # which revision is applied
alembic history        # full revision chain
alembic check          # detect unapplied changes
```

## Rollback

```bash
cd services/<service-name>
alembic downgrade -1   # one step back
alembic downgrade base # all the way back (destructive — confirm with user first)
```

## Common Patterns

### Add nullable column
```python
def upgrade():
    op.add_column("table_name", sa.Column("new_col", sa.String(), nullable=True))

def downgrade():
    op.drop_column("table_name", "new_col")
```

### Add index
```python
def upgrade():
    op.create_index("ix_table_col", "table_name", ["col_name"])

def downgrade():
    op.drop_index("ix_table_col", table_name="table_name")
```

### Rename column (two-step, safe)
Step 1 migration: add new column, copy data.
Step 2 migration (after deploy): drop old column.

## After Creating Migration

1. Read the generated file and confirm it's correct.
2. Run `alembic upgrade head` in the service directory.
3. Run the service tests to confirm nothing broke.
