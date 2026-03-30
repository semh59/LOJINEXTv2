"""Alembic smoke tests for location-service migrations."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command
from location_service.config import settings


def _alembic_config() -> Config:
    service_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(service_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(service_root / "alembic"))
    alembic_cfg.set_main_option("prepend_sys_path", str(service_root / "src"))
    return alembic_cfg


def test_alembic_upgrade_head_creates_live_pair_unique_index() -> None:
    alembic_cfg = _alembic_config()
    original_database_url = settings.database_url

    try:
        with PostgresContainer("postgres:16-alpine") as pg:
            database_url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
            settings.database_url = database_url
            alembic_cfg.set_main_option("sqlalchemy.url", database_url)
            command.upgrade(alembic_cfg, "head")

            async def _verify() -> None:
                engine = create_async_engine(database_url)
                try:
                    async with engine.connect() as conn:
                        route_pair_indexes = [
                            row[0]
                            for row in await conn.execute(
                                text(
                                    """
                                    SELECT indexname
                                    FROM pg_indexes
                                    WHERE schemaname = 'public'
                                      AND tablename = 'route_pairs'
                                    ORDER BY indexname
                                    """
                                )
                            )
                        ]
                finally:
                    await engine.dispose()

                assert "idx_route_pairs_live_unique" in route_pair_indexes
                assert "idx_route_pairs_active_unique" not in route_pair_indexes

            asyncio.run(_verify())
    finally:
        settings.database_url = original_database_url


def test_alembic_live_pair_uniqueness_migration_blocks_duplicate_drafts() -> None:
    alembic_cfg = _alembic_config()
    original_database_url = settings.database_url

    try:
        with PostgresContainer("postgres:16-alpine") as pg:
            database_url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
            settings.database_url = database_url
            alembic_cfg.set_main_option("sqlalchemy.url", database_url)
            command.upgrade(alembic_cfg, "0d5f12e97db6")

            origin_id = uuid.uuid4()
            destination_id = uuid.uuid4()

            async def _seed_duplicates() -> None:
                engine = create_async_engine(database_url)
                try:
                    async with engine.begin() as conn:
                        now = datetime(2026, 3, 30, tzinfo=UTC)
                        await conn.execute(
                            text(
                                """
                                INSERT INTO location_points (
                                    location_id,
                                    code,
                                    name_tr,
                                    name_en,
                                    normalized_name_tr,
                                    normalized_name_en,
                                    latitude_6dp,
                                    longitude_6dp,
                                    is_active,
                                    row_version,
                                    created_at_utc,
                                    updated_at_utc
                                )
                                VALUES
                                    (:origin_id, 'DUP_ORIGIN', 'Dup Origin', 'Dup Origin', 'DUP ORIGIN', 'DUP ORIGIN', 41.000001, 29.000001, true, 1, :now, :now),
                                    (:destination_id, 'DUP_DEST', 'Dup Dest', 'Dup Dest', 'DUP DEST', 'DUP DEST', 41.000002, 29.000002, true, 1, :now, :now)
                                """
                            ),
                            {
                                "origin_id": origin_id,
                                "destination_id": destination_id,
                                "now": now,
                            },
                        )
                        await conn.execute(
                            text(
                                """
                                INSERT INTO route_pairs (
                                    route_pair_id,
                                    pair_code,
                                    origin_location_id,
                                    destination_location_id,
                                    profile_code,
                                    pair_status,
                                    row_version,
                                    created_at_utc,
                                    updated_at_utc
                                )
                                VALUES
                                    (:pair_id_1, 'RP_00000000000000000000000001', :origin_id, :destination_id, 'TIR', 'DRAFT', 1, :now, :now),
                                    (:pair_id_2, 'RP_00000000000000000000000002', :origin_id, :destination_id, 'TIR', 'DRAFT', 1, :now, :now)
                                """
                            ),
                            {
                                "pair_id_1": uuid.uuid4(),
                                "pair_id_2": uuid.uuid4(),
                                "origin_id": origin_id,
                                "destination_id": destination_id,
                                "now": now,
                            },
                        )
                finally:
                    await engine.dispose()

            asyncio.run(_seed_duplicates())

            with pytest.raises(RuntimeError, match="duplicate ACTIVE/DRAFT route_pairs exist"):
                command.upgrade(alembic_cfg, "head")
    finally:
        settings.database_url = original_database_url


def test_alembic_upgrade_head_creates_processing_run_claim_columns() -> None:
    alembic_cfg = _alembic_config()
    original_database_url = settings.database_url

    try:
        with PostgresContainer("postgres:16-alpine") as pg:
            database_url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
            settings.database_url = database_url
            alembic_cfg.set_main_option("sqlalchemy.url", database_url)
            command.upgrade(alembic_cfg, "head")

            async def _verify() -> None:
                engine = create_async_engine(database_url)
                try:
                    async with engine.connect() as conn:
                        columns = {
                            row[0]
                            for row in await conn.execute(
                                text(
                                    """
                                    SELECT column_name
                                    FROM information_schema.columns
                                    WHERE table_schema = 'public'
                                      AND table_name = 'processing_runs'
                                    """
                                )
                            )
                        }
                finally:
                    await engine.dispose()

                assert {"claim_token", "claim_expires_at_utc", "claimed_by_worker"} <= columns

            asyncio.run(_verify())
    finally:
        settings.database_url = original_database_url
