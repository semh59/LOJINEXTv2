# Trip/Location — Backup & Restore Guide

## Overview

Both services use PostgreSQL as their primary data store. This guide covers logical backups using `pg_dump`/`pg_restore`.

Databases:

- `trip_service` — Trip lifecycle, enrichment, outbox, idempotency
- `location_service` — Points, route pairs, processing runs, route data

## Automated Backup

Use the backup utility script:

```bash
python ops/trip_location/backup_postgres.py \
    --host localhost \
    --port 5432 \
    --user lojinext \
    --password "$POSTGRES_PASSWORD" \
    --databases trip_service location_service \
    --output-dir ./backups \
    --format custom
```

This produces timestamped dump files:

```
backups/trip_service_20260330T120000Z.dump
backups/location_service_20260330T120000Z.dump
```

### Scheduled Backups

Add to cron:

```bash
# Daily backup at 02:00 UTC
0 2 * * * cd /opt/lojinext && python ops/trip_location/backup_postgres.py \
    --host postgres --user lojinext --password "$POSTGRES_PASSWORD" \
    --output-dir /backups/$(date +\%Y-\%m-\%d) 2>&1 | logger -t lojinext-backup
```

### Backup Verification

After backup, verify the dump is readable:

```bash
pg_restore --list backups/trip_service_20260330T120000Z.dump | head -20
```

## Restore

### Dry Run (Preview)

```bash
python ops/trip_location/restore_postgres.py \
    --host localhost --user lojinext --password "$POSTGRES_PASSWORD" \
    --database trip_service \
    --dump-file backups/trip_service_20260330T120000Z.dump \
    --dry-run
```

### Full Restore

> **⚠️ WARNING**: This will overwrite the target database contents.

```bash
# 1. Stop services to prevent writes during restore
docker compose -f docker-compose.prod.yml stop trip-api trip-enrichment trip-outbox trip-cleanup

# 2. Restore
python ops/trip_location/restore_postgres.py \
    --host localhost --user lojinext --password "$POSTGRES_PASSWORD" \
    --database trip_service \
    --dump-file backups/trip_service_20260330T120000Z.dump

# 3. Restart services
docker compose -f docker-compose.prod.yml start trip-api trip-enrichment trip-outbox trip-cleanup
```

Repeat for `location_service` if needed (stop location-api + location-processing first).

## Retention Policy

| Backup Type | Retention |
| ----------- | --------- |
| Daily       | 7 days    |
| Weekly      | 4 weeks   |
| Monthly     | 12 months |

## Redpanda (Kafka) Data

Redpanda data is stored in a Docker volume (`redpanda_data`). For Redpanda backup:

- Use host-level volume snapshots
- Or use `rpk topic produce/consume` for topic-level export

This is a host-level operational concern and is not automated by the service stack.
