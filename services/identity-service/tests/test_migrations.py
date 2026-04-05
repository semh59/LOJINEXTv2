from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from identity_service.crypto import decrypt_private_key


def _load_backfill_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "003_backfill_signing_key_ciphertext.py"
    )
    spec = importlib.util.spec_from_file_location("identity_backfill_migration", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_signing_key_backfill_requires_kek_env(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_backfill_module()
    monkeypatch.delenv("IDENTITY_KEY_ENCRYPTION_KEY_B64", raising=False)
    monkeypatch.delenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", raising=False)

    with pytest.raises(RuntimeError, match="IDENTITY_KEY_ENCRYPTION_KEY_B64 is required"):
        module.upgrade()


def test_signing_key_backfill_encrypts_existing_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_backfill_module()
    monkeypatch.setenv("IDENTITY_KEY_ENCRYPTION_KEY_B64", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    monkeypatch.setenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", "test-v1")

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        private_key_pem = "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"
        connection.execute(
            sa.text(
                """
                CREATE TABLE identity_signing_keys (
                    kid TEXT PRIMARY KEY,
                    private_key_pem TEXT NOT NULL,
                    private_key_ciphertext_b64 TEXT NULL,
                    private_key_kek_version TEXT NULL
                )
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO identity_signing_keys (
                    kid,
                    private_key_pem,
                    private_key_ciphertext_b64,
                    private_key_kek_version
                ) VALUES (:kid, :private_key_pem, NULL, NULL)
                """
            ),
            {"kid": "kid-001", "private_key_pem": private_key_pem},
        )
        monkeypatch.setattr(module.op, "get_bind", lambda: connection)

        module.upgrade()

        row = connection.execute(
            sa.text(
                """
                SELECT kid, private_key_pem, private_key_ciphertext_b64, private_key_kek_version
                FROM identity_signing_keys
                WHERE kid = 'kid-001'
                """
            )
        ).mappings().one()

    assert row["private_key_ciphertext_b64"]
    assert row["private_key_kek_version"] == "test-v1"
    assert decrypt_private_key(row["private_key_ciphertext_b64"], aad=row["kid"]) == private_key_pem
