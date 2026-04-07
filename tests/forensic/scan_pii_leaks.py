import asyncio
import json
import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Configuration
DB_URLS = {
    "identity": "postgresql+asyncpg://postgres:postgres@localhost:5432/identity_db",
    "driver": "postgresql+asyncpg://postgres:postgres@localhost:5432/driver_db",
}

# Regex for detecting raw email (simple version for leak detection)
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"\+\d{7,15}")  # E.164-ish


async def scan_pii_leaks():
    print("--- Starting PII Leak Forensic Scan ---")

    for service, url in DB_URLS.items():
        print(f"\nScanning {service} service...")
        engine = create_async_engine(url)
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session() as session:
            # 1. Audit Log Scan
            table_name = f"{service}_audit_log"
            print(f"  Checking {table_name} snapshots...")
            result = await session.execute(
                text(
                    f"SELECT audit_id, old_snapshot_json, new_snapshot_json FROM {table_name} LIMIT 100"
                )
            )
            for row in result:
                audit_id, old_snap, new_snap = row
                for snap_str in [old_snap, new_snap]:
                    if not snap_str:
                        continue
                    # snapshots are JSONB, so they might be strings or dicts depending on driver
                    snap = (
                        json.loads(snap_str) if isinstance(snap_str, str) else snap_str
                    )

                    # Check for leaks
                    snap_text = json.dumps(snap)

                    # Detection for Identity email masking
                    if service == "identity":
                        emails = EMAIL_REGEX.findall(snap_text)
                        for email in emails:
                            if "***" not in email:
                                print(
                                    f"  [CRITICAL] PII LEAK in {table_name} {audit_id}: Raw email found: {email}"
                                )

                    # Detection for Driver phone masking
                    if service == "driver":
                        # Check for phone leak
                        phones = PHONE_REGEX.findall(snap_text)
                        for phone in phones:
                            if "***" not in phone:
                                print(
                                    f"  [CRITICAL] PII LEAK in {table_name} {audit_id}: Raw phone found: {phone}"
                                )

            # 2. Outbox Scan
            outbox_table = f"{service}_outbox"
            print(f"  Checking {outbox_table} payloads...")
            result = await session.execute(
                text(f"SELECT outbox_id, payload_json FROM {outbox_table} LIMIT 100")
            )
            for row in result:
                outbox_id, payload_str = row
                payload = (
                    json.loads(payload_str)
                    if isinstance(payload_str, str)
                    else payload_str
                )
                payload_text = json.dumps(payload)

                # Outbox usually contains PII for downstream sync, we must ensure it's encrypted or documented
                # For this forensic, we just flag any raw emails/phones found in outbox as 'Information'
                emails = EMAIL_REGEX.findall(payload_text)
                if emails:
                    print(f"  [INFO] PII in Outbox {outbox_id}: {emails}")

        await engine.dispose()

    print("\n--- PII Leak Forensic Scan Finished ---")


if __name__ == "__main__":
    asyncio.run(scan_pii_leaks())
