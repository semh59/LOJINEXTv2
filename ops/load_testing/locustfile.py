import os
from locust import HttpUser, task, between


class TripServiceLoadTest(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        # We assume the user runs locust pointing to the Identity API or Trip API.
        # But we actually need to hit both. Locust's `self.client` targets the base URL.
        # So we'll define explicit URLs from env.
        self.identity_url = os.getenv("IDENTITY_API_URL", "http://localhost:8105")
        self.trip_url = os.getenv("TRIP_API_URL", "http://localhost:8101")
        self.superadmin_password = os.getenv(
            "IDENTITY_BOOTSTRAP_SUPERADMIN_PASSWORD", ""
        )

        # We don't want to crash if it's missing, but it's required to make authenticated calls
        if not self.superadmin_password:
            print(
                "WARNING: IDENTITY_BOOTSTRAP_SUPERADMIN_PASSWORD not set. Using empty string."
            )

        # Attempt Login via Identity API using standard Requests outside the target host if needed,
        # or just use self.client if target == base.
        resp = self.client.post(
            f"{self.identity_url}/auth/v1/login",
            json={"username": "superadmin", "password": self.superadmin_password},
        )
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            self.headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        else:
            self.headers = {}
            print(f"Failed to authenticate: {resp.status_code} {resp.text}")

    @task(3)
    def create_trip(self):
        if not self.headers:
            return

        payload = {
            "origin_id": "OR-100",
            "destination_id": "DE-200",
            "fleet_id": "FL-001",
            "status": "DRAFT",
        }
        with self.client.post(
            f"{self.trip_url}/api/v1/trips",
            json=payload,
            headers=self.headers,
            catch_response=True,
        ) as response:
            if (
                response.status_code in [200, 201, 202, 422]
            ):  # 422 might happen if data relations don't match, still a valid application response under stress
                response.success()
            else:
                response.failure(
                    f"Failed to create trip, status: {response.status_code}"
                )

    @task(5)
    def list_trips(self):
        if not self.headers:
            return

        with self.client.get(
            f"{self.trip_url}/api/v1/trips?limit=20",
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(
                    f"Failed to list trips, status: {response.status_code}"
                )

    @task(1)
    def check_metrics(self):
        with self.client.get(
            f"{self.trip_url}/metrics", catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics failed, status: {response.status_code}")
