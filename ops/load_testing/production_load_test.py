import os
import random
import string
import logging
from locust import HttpUser, task, between

# tortured removed, not standard. between is standard.
# Adding logging
logger = logging.getLogger(__name__)


class LojiNextProductionUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Bootstrap the user with an authentication token and discover resources."""
        self.base_url = os.getenv("NGINX_URL", "http://localhost:8180")
        self.superadmin_password = os.getenv(
            "IDENTITY_BOOTSTRAP_SUPERADMIN_PASSWORD", "change-me-immediately"
        )

        self.access_token = None
        self.headers = {}
        self.resources = {"drivers": [], "vehicles": [], "pairs": []}
        self._authenticate()
        if self.access_token:
            self._discover_resources()

    def _authenticate(self):
        """Obtain a real JWT from Identity Service."""
        resp = self.client.post(
            f"{self.base_url}/auth/v1/login",
            json={"username": "superadmin", "password": self.superadmin_password},
            name="/auth/v1/login",
        )
        if resp.status_code == 200:
            self.access_token = resp.json().get("access_token")
            self.headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "X-Request-ID": f"loadtest-{self._random_string(8)}",
            }
        else:
            logger.error(f"Authentication failed: {resp.status_code} {resp.text}")

    def _discover_resources(self):
        """Pre-fetch some IDs to build valid trip payloads."""
        # 1. Discover Drivers
        resp = self.client.get(
            f"{self.base_url}/api/v1/drivers?status=ACTIVE&per_page=10",
            headers=self.headers,
            name="/api/v1/drivers (discovery)",
        )
        if resp.status_code == 200:
            self.resources["drivers"] = [
                d["driver_id"] for d in resp.json().get("items", [])
            ]

        # 2. Discover Vehicles
        resp = self.client.get(
            f"{self.base_url}/api/v1/fleet/api/v1/vehicles?per_page=10",
            headers=self.headers,
            name="/api/v1/fleet/api/v1/vehicles (discovery)",
        )
        if resp.status_code == 200:
            self.resources["vehicles"] = [
                v["vehicle_id"] for v in resp.json().get("items", [])
            ]

        # 3. Discover Pairs
        resp = self.client.get(
            f"{self.base_url}/api/v1/locations/api/v1/pairs?per_page=10",
            headers=self.headers,
            name="/api/v1/locations/api/v1/pairs (discovery)",
        )
        if resp.status_code == 200:
            self.resources["pairs"] = [
                p["pair_id"] for p in resp.json().get("data", [])
            ]

    def _random_string(self, length=8):
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

    @task(10)
    def probe_points(self):
        """High-frequency point lookups (Read-heavy Location Service)."""
        if not self.access_token:
            return
        self.client.get(
            f"{self.base_url}/api/v1/locations/api/v1/points?per_page=20",
            headers=self.headers,
            name="/api/v1/locations/api/v1/points",
        )

    @task(2)
    def full_trip_lifecycle(self):
        """Most critical flow: Create Trip with full schema valid data."""
        if not self.access_token:
            return

        # Fallback if discovery failed or empty
        driver_id = (
            random.choice(self.resources["drivers"])
            if self.resources["drivers"]
            else f"GEN-{self._random_string(8)}"
        )
        vehicle_id = (
            random.choice(self.resources["vehicles"])
            if self.resources["vehicles"]
            else f"V-GEN-{self._random_string(4)}"
        )
        pair_id = (
            random.choice(self.resources["pairs"])
            if self.resources["pairs"]
            else f"P-GEN-{self._random_string(4)}"
        )

        trip_payload = {
            "trip_no": f"PROD-LT-{self._random_string(6)}",
            "route_pair_id": pair_id,
            "trip_start_local": "2026-04-10T09:00:00",
            "trip_timezone": "Europe/Istanbul",
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "tare_weight_kg": 15000,
            "gross_weight_kg": 40000,
            "net_weight_kg": 25000,
            "note": "Production Hardening Load Test",
        }

        resp = self.client.post(
            f"{self.base_url}/api/v1/trips",
            json=trip_payload,
            headers=self.headers,
            name="/api/v1/trips",
        )
        if resp.status_code != 201:
            logger.warning(f"Trip creation failed: {resp.status_code} {resp.text}")

    @task(3)
    def identity_check(self):
        """Identity Service /auth/v1/me validation."""
        if not self.access_token:
            return
        self.client.get(
            f"{self.base_url}/auth/v1/me", headers=self.headers, name="/auth/v1/me"
        )
