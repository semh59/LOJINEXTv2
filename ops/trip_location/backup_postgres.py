#!/usr/bin/env python3
"""PostgreSQL logical backup utility.

Usage:
    python backup_postgres.py --host HOST --user USER --password PASSWORD \
        [--databases trip_service location_service] [--output-dir ./backups]

Produces timestamped pg_dump files for each specified database.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime


def _run(cmd: list[str], env: dict[str, str]) -> bool:
    """Run a subprocess and return True on success."""
    print(f"  → {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ✗ FAILED (exit {result.returncode})")
        if result.stderr:
            print(f"    stderr: {result.stderr[:500]}")
        return False
    print("    ✓ OK")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Logical backup of Trip/Location databases"
    )
    parser.add_argument("--host", default="localhost", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--user", default="lojinext", help="PostgreSQL user")
    parser.add_argument("--password", required=True, help="PostgreSQL password")
    parser.add_argument(
        "--databases",
        nargs="+",
        default=["trip_service", "location_service"],
        help="Databases to back up",
    )
    parser.add_argument(
        "--output-dir", default="./backups", help="Output directory for dump files"
    )
    parser.add_argument(
        "--format", choices=["custom", "plain"], default="custom", help="pg_dump format"
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    env = {**os.environ, "PGPASSWORD": args.password}
    failures: list[str] = []

    print(f"\n{'=' * 60}")
    print(f"PostgreSQL Backup — {timestamp}")
    print(f"  Host: {args.host}:{args.port}")
    print(f"  Databases: {', '.join(args.databases)}")
    print(f"  Output: {args.output_dir}")
    print(f"{'=' * 60}\n")

    for db in args.databases:
        ext = "dump" if args.format == "custom" else "sql"
        output_file = os.path.join(args.output_dir, f"{db}_{timestamp}.{ext}")

        cmd = [
            "pg_dump",
            f"--host={args.host}",
            f"--port={args.port}",
            f"--username={args.user}",
            f"--dbname={db}",
            f"--format={args.format[0]}",
            f"--file={output_file}",
            "--no-owner",
            "--no-privileges",
        ]

        if not _run(cmd, env):
            failures.append(db)
        else:
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            print(f"    Size: {size_mb:.1f} MB → {output_file}")

    print(f"\n{'=' * 60}")
    if failures:
        print(f"BACKUP FAILED for: {', '.join(failures)}")
        sys.exit(1)
    else:
        print("BACKUP COMPLETED — all databases backed up successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
