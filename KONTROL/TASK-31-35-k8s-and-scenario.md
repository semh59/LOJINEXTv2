# TASK-31 — Kubernetes HPA: Tüm Servislere Ekle

## Amaç
Şu an sadece trip-service'te HPA var. Tüm servislere ekle.

## Kapsam
```
services/driver-service/k8s/base/hpa.yaml    (YENİ)
services/fleet-service/k8s/base/hpa.yaml     (YENİ)
services/identity-service/k8s/base/hpa.yaml  (YENİ)
services/location-service/k8s/base/hpa.yaml  (YENİ)
services/telegram-service/k8s/base/hpa.yaml  (YENİ)
```

## Referans
`services/trip-service/k8s/base/hpa.yaml` — kopyala, servis adını güncelle.

## Her servis için template

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {service-name}-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {service-name}
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

Servis isimleri: `driver-service`, `fleet-service`, `identity-service`, `location-service`, `telegram-service`

## Tamamlanma kriterleri
- [ ] 5 yeni hpa.yaml oluşturuldu
- [ ] Her dosyada `name` doğru servis adını içeriyor
- [ ] `minReplicas: 2` (high availability)
- [ ] YAML syntax valid

---

# TASK-32 — Kubernetes PodDisruptionBudget: Tüm Servislere Ekle

## Amaç
Şu an sadece trip-service'te PDB var. Rolling update sırasında minimum 1 pod ayakta kalmalı.

## Kapsam
```
services/driver-service/k8s/base/pdb.yaml    (YENİ)
services/fleet-service/k8s/base/pdb.yaml     (YENİ)
services/identity-service/k8s/base/pdb.yaml  (YENİ)
services/location-service/k8s/base/pdb.yaml  (YENİ)
services/telegram-service/k8s/base/pdb.yaml  (YENİ)
```

## Referans
`services/trip-service/k8s/base/pdb.yaml` — kopyala, servis adını güncelle.

## Template

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {service-name}-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: {service-name}
```

## Tamamlanma kriterleri
- [ ] 5 yeni pdb.yaml oluşturuldu
- [ ] Her dosyada `name` ve `matchLabels` doğru
- [ ] `minAvailable: 1`
- [ ] YAML syntax valid

---

# TASK-33 — Kubernetes NetworkPolicy: driver, fleet, location, telegram

## Amaç
Şu an sadece identity-service ve trip-service'te NetworkPolicy var. Diğer servislere ekle.

## Kapsam
```
services/driver-service/k8s/base/network-policy.yaml    (YENİ)
services/fleet-service/k8s/base/network-policy.yaml     (YENİ)
services/location-service/k8s/base/network-policy.yaml  (YENİ)
services/telegram-service/k8s/base/network-policy.yaml  (YENİ)
```

## Referans
`services/trip-service/k8s/base/network-policy.yaml` — kopyala, servis adını güncelle.

## Template (driver-service örnek)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: driver-service-network-policy
spec:
  podSelector:
    matchLabels:
      app: driver-service
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: nginx-gateway
        - podSelector:
            matchLabels:
              app: trip-service
      ports:
        - protocol: TCP
          port: 8103
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - protocol: TCP
          port: 5432
    - to:
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - protocol: TCP
          port: 6379
    - to:
        - podSelector:
            matchLabels:
              app: redpanda
      ports:
        - protocol: TCP
          port: 9092
    - to:
        - podSelector:
            matchLabels:
              app: identity-service
      ports:
        - protocol: TCP
          port: 8105
```

Her servis için port numarasını ve ingress kaynaklarını servisin gerçek bağımlılıklarına göre güncelle.

## Tamamlanma kriterleri
- [ ] 4 yeni network-policy.yaml oluşturuldu
- [ ] Ingress sadece meşru kaynaklardan (gateway, bağımlı servisler)
- [ ] Egress sadece gerekli hedeflere (postgres, redis, kafka, identity)
- [ ] YAML syntax valid

---

# TASK-34 — Istio Service Mesh + mTLS Kurulumu

## Amaç
Servisler arası güvenli iletişim için Istio service mesh kurulumu ve mTLS aktivasyonu.

## Kapsam
```
deploy/k8s/istio/  (YENİ DİZİN)
deploy/k8s/istio/peer-authentication.yaml
deploy/k8s/istio/destination-rules.yaml
deploy/k8s/istio/virtual-services.yaml
```

## peer-authentication.yaml

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: lojinext
spec:
  mtls:
    mode: STRICT
```

## destination-rules.yaml (her servis için)

```yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: trip-service
spec:
  host: trip-service
  trafficPolicy:
    tls:
      mode: ISTIO_MUTUAL
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        h2UpgradePolicy: UPGRADE
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
---
# Aynı şekilde: driver, fleet, identity, location, telegram servisleri
```

## virtual-services.yaml (timeout ve retry policy)

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: trip-service
spec:
  hosts:
    - trip-service
  http:
    - timeout: 10s
      retries:
        attempts: 3
        perTryTimeout: 3s
        retryOn: "5xx,reset,connect-failure"
```

## OPERATIONS.md güncellemesi

Istio kurulum adımlarını dokümante et:
```bash
istioctl install --set profile=production
kubectl label namespace lojinext istio-injection=enabled
kubectl apply -f deploy/k8s/istio/
```

## Tamamlanma kriterleri
- [ ] `peer-authentication.yaml` STRICT mTLS var
- [ ] Her servis için `DestinationRule` var
- [ ] Her servis için `VirtualService` timeout/retry var
- [ ] YAML syntax valid
- [ ] Kurulum talimatları dokümante edildi

---

# TASK-35 — live_master_scenario.py: Gerçek Akış Fix

## Amaç
Mevcut `tests/live_master_scenario.py` hardcoded ULID'ler kullanıyor, Fleet ve Driver kayıt adımları eksik, Kafka event doğrulaması yok. Gerçek end-to-end test yaz.

## Kapsam
```
tests/live_master_scenario.py
```

## Mevcut sorunlar
1. `route_pair_id`, `driver_id`, `vehicle_id` hardcoded ULID — seed'de olmayabilir
2. Fleet/Driver kayıt adımları yok
3. Kafka event doğrulaması yok
4. Correlation ID takibi eksik

## Yeni akış

```python
async def run_master_test():
    correlation_id = str(uuid.uuid4())
    headers = {"X-Correlation-ID": correlation_id}

    async with httpx.AsyncClient(timeout=30.0) as client:
        if not await wait_for_ready(client):
            return

        # PHASE 1: Authenticate
        token = await login(client, headers)
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}

        # PHASE 2: Register Fleet (vehicle + trailer)
        vehicle_id = await register_vehicle(client, auth_headers)
        logger.info(f"Vehicle registered: {vehicle_id}")

        # PHASE 3: Register Driver
        driver_id = await register_driver(client, auth_headers)
        logger.info(f"Driver registered: {driver_id}")

        # PHASE 4: Resolve route pair (location-service)
        route_pair_id = await resolve_route_pair(client, auth_headers)
        logger.info(f"Route pair: {route_pair_id}")

        # PHASE 5: Create trip
        trip_id = await create_trip(client, auth_headers, driver_id, vehicle_id, route_pair_id)
        logger.info(f"Trip created: {trip_id}")

        # PHASE 6: Verify outbox event (wait + poll)
        await asyncio.sleep(3)
        trip = await get_trip(client, auth_headers, trip_id)
        assert trip["status"] in ("COMPLETED", "PENDING_REVIEW"), f"Unexpected status: {trip['status']}"

        # PHASE 7: Correlation ID takibi
        logger.info(f"Correlation chain: {correlation_id}")
        logger.info("✅ Master scenario PASSED")
```

Her fonksiyon (register_vehicle, register_driver, vb.) ayrı async fonksiyon olarak yaz. Hardcoded ID kullanma — her çalışmada gerçek kayıt yap.

## Tamamlanma kriterleri
- [ ] Hardcoded ULID yok
- [ ] Fleet ve Driver kayıt adımları var
- [ ] Route pair gerçek API'den alınıyor
- [ ] Trip oluşturma beklenen status'u doğruluyor
- [ ] Correlation ID tüm request'lere ekleniyor
- [ ] Syntax error yok
