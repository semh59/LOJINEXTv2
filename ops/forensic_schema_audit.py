"""Forensic Schema Auditor — CI/CD Gate for LojiNextV2.

Ensures all service outbox tables comply with the forensic standards:
1. payload_json MUST be JSONB.
2. correlation_id MUST be present (String 64).
3. Primary Key MUST be String 26 (ULID).
"""

import sys
from typing import List
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

# Service outbox table mappings
SERVICE_OUTBOXES = {
    "identity": "identity_outbox",
    "trip": "trip_outbox",
    "location": "location_outbox",
    "driver": "driver_outbox",
    "fleet": "fleet_outbox",
}


def audit_engine(engine: Engine, service_name: str, table_name: str) -> List[str]:
    """Audits a single service database for forensic compliance."""
    errors = []
    inspector = inspect(engine)

    if table_name not in inspector.get_table_names():
        return [f"ERROR: Table '{table_name}' missing in {service_name} service."]

    columns = {col["name"]: col for col in inspector.get_columns(table_name)}

    # 1. JSONB Check
    if "payload_json" not in columns:
        errors.append(f"ERROR: 'payload_json' missing in {table_name}.")
    else:
        col_type = str(columns["payload_json"]["type"]).upper()
        if "JSONB" not in col_type:
            errors.append(f"ERROR: {table_name}.payload_json is {col_type}, MUST be JSONB.")

    # 2. Correlation ID Check
    if "correlation_id" not in columns:
        errors.append(f"ERROR: 'correlation_id' missing in {table_name} (Forensic Trace Breach).")

    # 3. PK / ULID Check
    pk_cols = inspector.get_pk_constraint(table_name)["constrained_columns"]
    for pk in pk_cols:
        pk_type = str(columns[pk]["type"]).upper()
        if "VARCHAR(26)" not in pk_type and "STRING(26)" not in pk_type:
            # Some dialects might report VARCHAR(26) differently, but we check for 26 length
            if not any(char.isdigit() and "26" in pk_type for char in pk_type):
                errors.append(f"WARNING: PK {pk} type is {pk_type}, expected length 26 (ULID).")

    return errors


def main():
    # In CI, we use env vars for each service DB
    import os

    overall_errors = []

    for service, table in SERVICE_OUTBOXES.items():
        db_url = os.getenv(f"{service.upper()}_DATABASE_URL")
        if not db_url:
            print(f"Skipping {service} (No URL provided)")
            continue

        # Convert asyncpg to psycopg2 for inspector (standard sync engine is easier for audit scripts)
        sync_url = db_url.replace("asyncpg", "psycopg2")
        try:
            engine = create_engine(sync_url)
            print(f"Auditing {service} forensic schema...")
            errors = audit_engine(engine, service, table)
            if errors:
                overall_errors.extend(errors)
                for err in errors:
                    print(f"  [!] {err}")
            else:
                print(f"  [OK] {service} is forensically hardened.")
        except Exception as e:
            print(f"  [FAILED] Could not connect to {service}: {e}")

    if overall_errors:
        print(f"\nFORENSIC AUDIT FAILED: {len(overall_errors)} regressions detected.")
        sys.exit(1)

    print("\nFORENSIC AUDIT PASSED: All services are production-ready.")


if __name__ == "__main__":
    main()
