#!/usr/bin/env python3
"""PostgreSQL restore utility.

Usage:
    python restore_postgres.py --host HOST --user USER --password PASSWORD \
        --database trip_service --dump-file backups/trip_service_20260330T120000Z.dump \
        [--dry-run]

Restores a pg_dump backup into the specified database.
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
        description="Restore Trip/Location database from dump"
    )
    parser.add_argument("--host", default="localhost", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--user", default="lojinext", help="PostgreSQL user")
    parser.add_argument("--password", required=True, help="PostgreSQL password")
    parser.add_argument("--database", required=True, help="Target database name")
    parser.add_argument("--dump-file", required=True, help="Path to the dump file")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.dump_file):
        print(f"ERROR: Dump file not found: {args.dump_file}")
        sys.exit(1)

    env = {**os.environ, "PGPASSWORD": args.password}
    is_custom = args.dump_file.endswith(".dump")

    print(f"\n{'=' * 60}")
    print(f"PostgreSQL Restore — {datetime.now(UTC).isoformat()}")
    print(f"  Host:     {args.host}:{args.port}")
    print(f"  Database: {args.database}")
    print(f"  Dump:     {args.dump_file}")
    print(f"  Format:   {'custom' if is_custom else 'plain'}")
    if args.dry_run:
        print("  Mode:     DRY RUN (no changes will be made)")
    print(f"{'=' * 60}\n")

    if is_custom:
        cmd = [
            "pg_restore",
            f"--host={args.host}",
            f"--port={args.port}",
            f"--username={args.user}",
            f"--dbname={args.database}",
            "--no-owner",
            "--no-privileges",
            "--clean",
            "--if-exists",
        ]
        if args.dry_run:
            cmd.append("--list")
        cmd.append(args.dump_file)
    else:
        cmd = [
            "psql",
            f"--host={args.host}",
            f"--port={args.port}",
            f"--username={args.user}",
            f"--dbname={args.database}",
            f"--file={args.dump_file}",
        ]
        if args.dry_run:
            print("  DRY RUN: would execute psql with the given dump file")
            print(f"  → {' '.join(cmd)}")
            sys.exit(0)

    if _run(cmd, env):
        print(f"\n{'=' * 60}")
        if args.dry_run:
            print("DRY RUN COMPLETE — no changes made")
        else:
            print("RESTORE COMPLETED — database restored successfully")
        sys.exit(0)
    else:
        print(f"\n{'=' * 60}")
        print("RESTORE FAILED — see errors above")
        sys.exit(1)


if __name__ == "__main__":
    main()
