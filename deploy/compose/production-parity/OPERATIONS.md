# LOJINEXT Phase 5: Operations Manual 🛠️

This manual provides instructions for managing the hardened V2.1 production-parity stack.

## 1. Environment Management

All commands should be run from `deploy/compose/production-parity/`.

### Toggling Security Modes

Edit the `.env` file to adjust security strictness:

- **Strict S2S Audience Check**: Set `IDENTITY_AUTH_STRICT_AUDIENCE_CHECK=true` to reject service tokens that don't match the platform audience exactly.
- **Port Mapping**: Change `NGINX_PORT` to avoid host conflicts.

### Database Seeding

To perform a clean seed of the parity environment:

```powershell
# Reset volumes (WARNING: Deletes all data)
docker compose down -v
docker compose up -d postgres

# Apply migrations
docker compose run --rm trip-api alembic upgrade head
docker compose run --rm driver-api alembic upgrade head
docker compose run --rm fleet-api alembic upgrade head
docker compose run --rm location-api alembic upgrade head
docker compose run --rm identity-api alembic upgrade head

# Seed Data
cat seed_parity_data.sql | docker exec -i lojinext-parity-postgres-1 psql -U lojinext -d trip_service
# (Repeat for other DBs if using separate ones, or use the consolidated script)
```

## 2. Verification Tools

### E2E Tracing Simulation

Run the comprehensive trace simulation to verify inter-service communication through the Nginx gateway:

```powershell
python trigger_parity_trace.py
```

### Log Inspection

All services use 3x10MB log rotation. Inspect active logs:

```powershell
docker compose logs -f trip-api
```

## 3. Resource Monitoring

Verify that limits (512MB RAM) are being enforced:

```powershell
docker stats
```
