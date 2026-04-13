# TASK-16 — AlertManager: Tüm Servisler İçin Kural Seti

## Amaç
Şu an sadece trip-service için Prometheus alert kuralları var. Tüm servisler için standart kural seti oluştur.

## Kapsam
```
ops/monitoring/prometheus/alert_rules.yml
```

## Eklenecek kural grupları

Mevcut `trip_service_alerts` grubunu model alarak her servis için:

```yaml
groups:
  # Mevcut trip_service_alerts kalır

  - name: outbox_alerts
    rules:
      - alert: OutboxDeadLetterDetected
        expr: sum by (service) (increase(trip_outbox_dead_letter_total[5m])) > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Dead-letter event detected in {{ $labels.service }}"
          description: "An outbox event has reached DEAD_LETTER status and will not be retried automatically."

      - alert: OutboxHighPendingCount
        expr: |
          sum by (service) (
            pg_stat_user_tables_n_live_tup{relname=~".*_outbox"}
          ) > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High outbox pending count for {{ $labels.service }}"

  - name: service_health_alerts
    rules:
      - alert: ServiceReadinessFailure
        expr: up{job=~".*-service"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is DOWN"
          description: "Service has been unreachable for 2 minutes."

      - alert: ServiceHighErrorRate
        expr: |
          sum by (service) (rate(http_requests_total{status_code=~"5.."}[5m]))
          /
          sum by (service) (rate(http_requests_total[5m])) > 0.05
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High 5xx error rate on {{ $labels.service }}"

      - alert: WorkerHeartbeatStale
        expr: |
          (time() - worker_last_heartbeat_timestamp_seconds) > 90
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Worker heartbeat stale for {{ $labels.worker_name }}"

  - name: kafka_alerts
    rules:
      - alert: KafkaConsumerLag
        expr: kafka_consumer_group_lag > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High Kafka consumer lag: {{ $labels.group }}/{{ $labels.topic }}"

      - alert: KafkaProducerErrors
        expr: sum by (service) (rate(kafka_producer_record_error_rate[5m])) > 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Kafka producer errors in {{ $labels.service }}"

  - name: circuit_breaker_alerts
    rules:
      - alert: CircuitBreakerOpen
        expr: sum by (service, breaker_name) (rate(trip_cb_state_changes_total{state="OPEN"}[5m])) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Circuit breaker OPEN: {{ $labels.breaker_name }} in {{ $labels.service }}"
```

## Tamamlanma kriterleri
- [ ] `alert_rules.yml` güncellendi
- [ ] `outbox_alerts` grubu var
- [ ] `service_health_alerts` grubu var
- [ ] `kafka_alerts` grubu var
- [ ] `circuit_breaker_alerts` grubu var
- [ ] YAML syntax valid (`yamllint alert_rules.yml`)
