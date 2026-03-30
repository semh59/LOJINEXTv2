# Trip/Location — Incident Runbooks

## 1. Stuck Enrichment Worker

**Symptoms**: Trips stay in `DRAFT` status indefinitely, enrichment heartbeat shows `stale` in `/ready`.

**Investigation**:

```bash
# Check enrichment worker logs
docker compose logs --tail=100 trip-enrichment

# Check for stuck claims in DB
docker compose exec postgres psql -U lojinext -d trip_service -c \
  "SELECT trip_id, enrichment_status, claimed_at_utc, claim_expires_at_utc FROM trips WHERE enrichment_status = 'CLAIMED' ORDER BY claimed_at_utc;"
```

**Resolution**:

1. If worker is crashed → restart: `docker compose restart trip-enrichment`
2. If claims are past TTL → they will auto-expire and be reclaimed on next poll
3. If worker keeps crashing → check `TRIP_ENRICHMENT_CLAIM_TTL_SECONDS` and downstream dependency logs

---

## 2. Stale Outbox Rows

**Symptoms**: `outbox_dead_letter_total` metric increases, events not reaching Kafka.

**Investigation**:

```bash
# Check outbox relay logs
docker compose logs --tail=100 trip-outbox

# Check Redpanda health
docker compose exec redpanda rpk cluster health

# Check outbox state
docker compose exec postgres psql -U lojinext -d trip_service -c \
  "SELECT publish_status, COUNT(*) FROM trip_outbox GROUP BY publish_status;"
```

**Resolution**:

1. If Redpanda is unhealthy → restart: `docker compose restart redpanda`
2. If PUBLISHING rows are stuck (past claim TTL) → they will auto-expire
3. If DEAD_LETTER count is high → investigate `last_error_code` values for root cause

---

## 3. Processing Worker Hung

**Symptoms**: Location `/ready` returns 503, processing worker heartbeat stale.

**Investigation**:

```bash
# Check processing worker logs
docker compose logs --tail=100 location-processing

# Check for stuck processing runs
docker compose exec postgres psql -U lojinext -d location_service -c \
  "SELECT processing_run_id, run_status, started_at_utc, claim_expires_at_utc FROM processing_runs WHERE run_status = 'RUNNING' ORDER BY started_at_utc;"
```

**Resolution**:

1. If worker is crashed → restart: `docker compose restart location-processing`
2. If stuck runs exist → they will be reclaimed when claim expires (see `LOCATION_PROCESSING_CLAIM_TTL_SECONDS`)
3. If provider is timing out → check `LOCATION_PROVIDER_TIMEOUT_MS` and Mapbox/ORS status

---

## 4. Database Connection Pool Exhaustion

**Symptoms**: 500 errors across services, logs show "too many connections".

**Investigation**:

```bash
docker compose exec postgres psql -U lojinext -d trip_service -c \
  "SELECT count(*) FROM pg_stat_activity;"
```

**Resolution**:

1. Check for long-running queries: `SELECT pid, query, state, query_start FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start;`
2. Kill long-running queries if needed: `SELECT pg_terminate_backend(pid);`
3. Scale down workers if connection pressure is too high
4. Consider increasing `max_connections` in PostgreSQL config

---

## 5. Provider Outage (Mapbox/ORS)

**Symptoms**: Location `/ready` returns 503 with `mapbox_live: unavailable` or `ors_live: unavailable`.

**Investigation**:

```bash
# Check cached probe result
curl -s http://localhost:8103/ready | python -m json.tool

# Check provider metrics
curl -s http://localhost:8103/metrics | grep provider_call_errors
```

**Resolution**:

1. If Mapbox is down → check https://status.mapbox.com
2. If ORS is down → check ORS provider status
3. Processing runs will fail gracefully and be retried when provider recovers
4. If outage is prolonged → disable ORS validation: `LOCATION_ENABLE_ORS_VALIDATION=false`

---

## 6. Cleanup Worker Not Running

**Symptoms**: Trip `/ready` returns 503 with `cleanup_worker: stale`, idempotency records accumulate.

**Investigation**:

```bash
docker compose logs --tail=50 trip-cleanup
```

**Resolution**:

1. Restart: `docker compose restart trip-cleanup`
2. If crashes on startup → check DB connectivity
3. Idempotency records will be cleaned up once the worker recovers
