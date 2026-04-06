from __future__ import annotations

import asyncio
from pathlib import Path
import os
from datetime import datetime, UTC

from alembic import command
from alembic.config import Config
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from identity_service.crypto import decrypt_private_key, encrypt_private_key

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(db_url: str) -> Config:
    os.environ["IDENTITY_DATABASE_URL"] = db_url
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    config.set_main_option("prepend_sys_path", str(SERVICE_ROOT / "src"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


@pytest_asyncio.fixture
async def clean_db_url() -> str:
    global_pg_url = os.environ["IDENTITY_DATABASE_URL"]
    engine = create_async_engine(global_pg_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(sa.text("CREATE SCHEMA public"))
    await engine.dispose()
    return global_pg_url


async def _get_table_columns(db_url: str, table_name: str) -> list[str]:
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        res = await conn.execute(
            sa.text(
                f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position"
            )
        )
        columns = [row[0] for row in res.fetchall()]
    await engine.dispose()
    return columns


@pytest.mark.asyncio
async def test_signing_key_backfill_requires_kek_env(
    clean_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _alembic_config(clean_db_url)
    await asyncio.to_thread(command.upgrade, config, "002_signing_key_ciphertext")

    monkeypatch.delenv("IDENTITY_KEY_ENCRYPTION_KEY_B64", raising=False)
    monkeypatch.delenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", raising=False)

    with pytest.raises(Exception, match="IDENTITY_KEY_ENCRYPTION_KEY_B64 is required"):
        await asyncio.to_thread(command.upgrade, config, "003_backfill_key_ciphertext")


@pytest.mark.asyncio
async def test_signing_key_backfill_encrypts_existing_rows(
    clean_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _alembic_config(clean_db_url)
    monkeypatch.setenv(
        "IDENTITY_KEY_ENCRYPTION_KEY_B64",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    monkeypatch.setenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", "test-v1")

    await asyncio.to_thread(command.upgrade, config, "002_signing_key_ciphertext")

    engine = create_async_engine(clean_db_url)
    private_key_pem = "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO identity_signing_keys (
                    kid,
                    algorithm,
                    public_key_pem,
                    is_active,
                    private_key_pem,
                    private_key_ciphertext_b64,
                    private_key_kek_version,
                    created_at_utc,
                    retired_at_utc
                ) VALUES (:kid, 'RS256', 'pub', true, :private_key_pem, NULL, NULL, '2026-04-05T00:00:00+00:00', NULL)
                """
            ),
            {"kid": "kid-001", "private_key_pem": private_key_pem},
        )
    await engine.dispose()

    # Apply backfill
    await asyncio.to_thread(command.upgrade, config, "003_backfill_key_ciphertext")

    engine = create_async_engine(clean_db_url)
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    sa.text(
                        """
                    SELECT kid, private_key_pem, private_key_ciphertext_b64, private_key_kek_version
                    FROM identity_signing_keys
                    WHERE kid = 'kid-001'
                    """
                    )
                )
            )
            .mappings()
            .one()
        )
    await engine.dispose()

    assert row["private_key_ciphertext_b64"]
    assert row["private_key_kek_version"] == "test-v1"
    assert (
        decrypt_private_key(row["private_key_ciphertext_b64"], aad=row["kid"])
        == private_key_pem
    )


@pytest.mark.asyncio
async def test_head_migrations_upgrade_on_postgres(
    clean_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _alembic_config(clean_db_url)
    monkeypatch.setenv(
        "IDENTITY_KEY_ENCRYPTION_KEY_B64",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    monkeypatch.setenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", "test-v1")

    await asyncio.to_thread(command.upgrade, config, "head")

    outbox_cols = await _get_table_columns(clean_db_url, "identity_outbox")
    assert "outbox_id" in outbox_cols
    audit_cols = await _get_table_columns(clean_db_url, "identity_audit_log")
    assert "audit_id" in audit_cols
    worker_cols = await _get_table_columns(clean_db_url, "identity_worker_heartbeats")
    assert "worker_name" in worker_cols


@pytest.mark.asyncio
async def test_signing_key_downgrade_restores_plaintext_when_kek_present(
    clean_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _alembic_config(clean_db_url)
    monkeypatch.setenv(
        "IDENTITY_KEY_ENCRYPTION_KEY_B64",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    monkeypatch.setenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", "test-v1")

    await asyncio.to_thread(command.upgrade, config, "004_drop_plaintext_signing_key")

    engine = create_async_engine(clean_db_url)
    private_key_pem = (
        "-----BEGIN PRIVATE KEY-----\nrestored-key\n-----END PRIVATE KEY-----"
    )
    ciphertext = encrypt_private_key(private_key_pem, aad="kid-001")

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO identity_signing_keys (
                    kid,
                    algorithm,
                    public_key_pem,
                    private_key_ciphertext_b64,
                    private_key_kek_version,
                    is_active,
                    created_at_utc,
                    retired_at_utc
                ) VALUES (:kid, :alg, :pub, :enc, :kek, :act, :cre, :ret)
                """
            ),
            {
                "kid": "kid-001",
                "alg": "RS256",
                "pub": "-----BEGIN PUBLIC KEY-----\npub\n-----END PUBLIC KEY-----",
                "enc": ciphertext,
                "kek": "test-v1",
                "act": True,
                "cre": datetime(2026, 4, 5, tzinfo=UTC),
                "ret": None,
            },
        )
    await engine.dispose()

    await asyncio.to_thread(command.downgrade, config, "003_backfill_key_ciphertext")

    engine = create_async_engine(clean_db_url)
    async with engine.connect() as connection:
        row = await connection.execute(
            sa.text(
                """
                SELECT private_key_pem, private_key_ciphertext_b64, private_key_kek_version
                FROM identity_signing_keys
                WHERE kid = 'kid-001'
                """
            )
        )
        row = row.fetchone()
    await engine.dispose()

    assert row is not None
    assert row[0] == private_key_pem
    assert row[1] == ciphertext
    assert row[2] == "test-v1"


@pytest.mark.asyncio
async def test_signing_key_downgrade_requires_kek_env(
    clean_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _alembic_config(clean_db_url)
    monkeypatch.setenv(
        "IDENTITY_KEY_ENCRYPTION_KEY_B64",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    monkeypatch.setenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", "test-v1")

    await asyncio.to_thread(command.upgrade, config, "004_drop_plaintext_signing_key")

    engine = create_async_engine(clean_db_url)
    ciphertext = encrypt_private_key(
        "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----", aad="kid-002"
    )

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO identity_signing_keys (
                    kid,
                    algorithm,
                    public_key_pem,
                    private_key_ciphertext_b64,
                    private_key_kek_version,
                    is_active,
                    created_at_utc,
                    retired_at_utc
                ) VALUES (:kid, :alg, :pub, :enc, :kek, :act, :cre, :ret)
                """
            ),
            {
                "kid": "kid-002",
                "alg": "RS256",
                "pub": "-----BEGIN PUBLIC KEY-----\npub\n-----END PUBLIC KEY-----",
                "enc": ciphertext,
                "kek": "test-v1",
                "act": True,
                "cre": datetime(2026, 4, 5, tzinfo=UTC),
                "ret": None,
            },
        )
    await engine.dispose()

    monkeypatch.delenv("IDENTITY_KEY_ENCRYPTION_KEY_B64", raising=False)
    monkeypatch.delenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", raising=False)

    with pytest.raises(
        Exception,
        match="IDENTITY_KEY_ENCRYPTION_KEY_B64 is required to downgrade signing keys.",
    ):
        await asyncio.to_thread(
            command.downgrade, config, "003_backfill_key_ciphertext"
        )
