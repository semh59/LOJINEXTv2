"""Alembic smoke tests for trip-service schema baseline."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command


def test_alembic_upgrade_head_on_empty_postgres() -> None:
    service_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(service_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(service_root / "alembic"))
    alembic_cfg.set_main_option("prepend_sys_path", str(service_root / "src"))

    with PostgresContainer("postgres:16-alpine") as pg:
        database_url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(alembic_cfg, "head")

        async def _verify() -> None:
            engine = create_async_engine(database_url)
            try:
                async with engine.connect() as conn:
                    tables = [
                        row[0]
                        for row in await conn.execute(
                            text(
                                """
                                SELECT tablename
                                FROM pg_catalog.pg_tables
                                WHERE schemaname = 'public'
                                  AND (tablename = 'alembic_version' OR tablename LIKE 'trip_%')
                                ORDER BY tablename
                                """
                            )
                        )
                    ]
                    trip_columns = [
                        row[0]
                        for row in await conn.execute(
                            text(
                                """
                                SELECT column_name
                                FROM information_schema.columns
                                WHERE table_name = 'trip_trips'
                                ORDER BY column_name
                                """
                            )
                        )
                    ]
                    trip_indexes = [
                        row[0]
                        for row in await conn.execute(
                            text(
                                """
                                SELECT indexname
                                FROM pg_indexes
                                WHERE schemaname = 'public'
                                  AND tablename = 'trip_trips'
                                ORDER BY indexname
                                """
                            )
                        )
                    ]
            finally:
                await engine.dispose()

            assert tables == [
                "alembic_version",
                "trip_idempotency_records",
                "trip_outbox",
                "trip_trip_delete_audit",
                "trip_trip_enrichment",
                "trip_trip_evidence",
                "trip_trip_timeline",
                "trip_trips",
            ]
            assert "route_pair_id" in trip_columns
            assert "origin_name_snapshot" in trip_columns
            assert "destination_name_snapshot" in trip_columns
            assert "planned_duration_s" in trip_columns
            assert "planned_end_utc" in trip_columns
            assert "review_reason_code" in trip_columns
            assert "source_reference_key" in trip_columns
            assert "uq_trips_empty_return_base_trip" in trip_indexes
            assert "uq_trips_source_reference_key" in trip_indexes

        asyncio.run(_verify())
