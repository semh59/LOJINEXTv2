import uuid

import httpx


def trigger_driver_trace():
    base_url = "http://localhost:8180"
    correlation_id = str(uuid.uuid4())
    print(f"Starting Driver mutation with Correlation-ID: {correlation_id}")

    # 1. Login
    print("Authenticating...")
    login_resp = httpx.post(
        f"{base_url}/auth/v1/login",
        json={"username": "superadmin", "password": "change-me-immediately"},
        headers={"X-Correlation-ID": correlation_id},
    )
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.text}")
        return
    token = login_resp.json()["access_token"]

    # 2. Create Driver
    print("Creating Driver...")
    driver_data = {
        "company_driver_code": f"DRV-{uuid.uuid4().hex[:6]}",
        "full_name": "Trace Verification Driver",
        "phone": "+90555" + "".join([str(uuid.uuid4().int % 10) for _ in range(7)]),
        "license_class": "CE",
        "employment_start_date": "2024-01-01",
    }
    create_resp = httpx.post(
        f"{base_url}/api/v1/drivers",
        json=driver_data,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Correlation-ID": correlation_id,
            "X-Request-ID": correlation_id,
        },
        timeout=10.0,
    )

    if create_resp.status_code not in (201, 200):
        print(f"Driver creation failed: {create_resp.status_code} - {create_resp.text}")
        return

    driver_id = create_resp.json().get("driver_id")
    print(f"Driver created successfully: {driver_id}")
    print(f"Verification Correlation-ID: {correlation_id}")


if __name__ == "__main__":
    trigger_driver_trace()
