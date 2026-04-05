"""backfill encrypted signing keys

Revision ID: 003_backfill_signing_key_ciphertext
Revises: 002_add_signing_key_ciphertext_columns
Create Date: 2026-04-05
"""

from __future__ import annotations

import base64
import os

from alembic import op
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import sqlalchemy as sa


revision = "003_backfill_signing_key_ciphertext"
down_revision = "002_add_signing_key_ciphertext_columns"
branch_labels = None
depends_on = None


def _decode_kek() -> bytes:
    raw = os.getenv("IDENTITY_KEY_ENCRYPTION_KEY_B64", "").strip()
    if not raw:
        raise RuntimeError(
            "IDENTITY_KEY_ENCRYPTION_KEY_B64 is required for signing-key backfill."
        )
    padding = "=" * (-len(raw) % 4)
    decoded = base64.urlsafe_b64decode(f"{raw}{padding}")
    if len(decoded) != 32:
        raise RuntimeError(
            "IDENTITY_KEY_ENCRYPTION_KEY_B64 must decode to exactly 32 bytes."
        )
    return decoded


def _kek_version() -> str:
    version = os.getenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", "").strip()
    if not version:
        raise RuntimeError(
            "IDENTITY_KEY_ENCRYPTION_KEY_VERSION is required for signing-key backfill."
        )
    return version


def _encrypt(private_key_pem: str, *, kid: str, key_bytes: bytes) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key_bytes).encrypt(
        nonce, private_key_pem.encode("utf-8"), kid.encode("utf-8")
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def upgrade() -> None:
    key_bytes = _decode_kek()
    version = _kek_version()
    bind = op.get_bind()
    rows = (
        bind.execute(sa.text("SELECT kid, private_key_pem FROM identity_signing_keys"))
        .mappings()
        .all()
    )
    for row in rows:
        ciphertext = _encrypt(
            row["private_key_pem"], kid=row["kid"], key_bytes=key_bytes
        )
        bind.execute(
            sa.text(
                """
                UPDATE identity_signing_keys
                SET private_key_ciphertext_b64 = :ciphertext,
                    private_key_kek_version = :version
                WHERE kid = :kid
                """
            ),
            {"ciphertext": ciphertext, "version": version, "kid": row["kid"]},
        )
    missing = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM identity_signing_keys
            WHERE private_key_ciphertext_b64 IS NULL OR private_key_kek_version IS NULL
            """
        )
    ).scalar_one()
    if int(missing or 0) != 0:
        raise RuntimeError("Signing-key backfill did not populate every row.")


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE identity_signing_keys
            SET private_key_ciphertext_b64 = NULL,
                private_key_kek_version = NULL
            """
        )
    )
