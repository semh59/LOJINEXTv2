# TASK-26 — Driver-Service: GitHub Actions CI/CD Pipeline

## Amaç
Driver-service için trip-service CI/CD pipeline'ını model alarak GitHub Actions pipeline oluştur.

## Kapsam
```
services/driver-service/.github/workflows/ci.yaml  (YENİ)
```

## Referans
`services/trip-service/.github/workflows/ci.yaml` — kopyala, namespace değiştir.

## Değişiklikler trip-service'ten farkı

```yaml
name: Driver Service CI

on:
  push:
    branches: [main, develop]
    paths:
      - "services/driver-service/**"
      - "packages/**"
  pull_request:
    branches: [main]
    paths:
      - "services/driver-service/**"
      - "packages/**"

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: |
          pip install -e packages/platform-auth
          pip install -e packages/platform-common
          pip install -e services/driver-service
      - name: Lint (ruff)
        run: ruff check services/driver-service/src/
      - name: Type check (mypy)
        run: mypy services/driver-service/src/ --ignore-missing-imports || true
      - name: Tests
        run: pytest services/driver-service/tests/ -v --tb=short

  build-and-push:
    needs: lint-and-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Login to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ secrets.REGISTRY_URL }}
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: services/driver-service/Dockerfile
          push: true
          tags: |
            ${{ secrets.REGISTRY_URL }}/driver-service:${{ github.sha }}
            ${{ secrets.REGISTRY_URL }}/driver-service:latest

  security-scan:
    needs: build-and-push
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: "${{ secrets.REGISTRY_URL }}/driver-service:${{ github.sha }}"
          severity: "CRITICAL,HIGH"
          exit-code: "1"
```

## Tamamlanma kriterleri
- [ ] `ci.yaml` oluşturuldu
- [ ] path trigger doğru (`driver-service/**`)
- [ ] lint, test, build, security-scan adımları var
- [ ] YAML syntax valid

---

# TASK-27 — Fleet-Service: GitHub Actions CI/CD Pipeline

Aynı pattern, `driver` → `fleet` değiştir.

```
services/fleet-service/.github/workflows/ci.yaml  (YENİ)
```

path trigger: `"services/fleet-service/**"`  
Dockerfile: `services/fleet-service/Dockerfile`  
image tag: `fleet-service`

---

# TASK-28 — Identity-Service: GitHub Actions CI/CD Pipeline

Aynı pattern, `driver` → `identity` değiştir.

```
services/identity-service/.github/workflows/ci.yaml  (YENİ)
```

path trigger: `"services/identity-service/**"`

---

# TASK-29 — Location-Service: GitHub Actions CI/CD Pipeline

Aynı pattern, `driver` → `location` değiştir.

```
services/location-service/.github/workflows/ci.yaml  (YENİ)
```

path trigger: `"services/location-service/**"`

---

# TASK-30 — Telegram-Service: GitHub Actions CI/CD Pipeline

Aynı pattern, `driver` → `telegram` değiştir.

```
services/telegram-service/.github/workflows/ci.yaml  (YENİ)
```

path trigger: `"services/telegram-service/**"`

---

## Tüm CI/CD görevleri (26-30) için ortak tamamlanma kriterleri
- [ ] Her servis için `ci.yaml` oluşturuldu (5 dosya)
- [ ] Her dosyada path trigger doğru servis dizinini işaret ediyor
- [ ] lint → test → build → security-scan adımları var
- [ ] YAML syntax valid (tüm dosyalar)
