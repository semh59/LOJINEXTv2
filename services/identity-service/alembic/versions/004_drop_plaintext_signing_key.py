"""drop plaintext signing key column

Revision ID: 004_drop_plaintext_signing_key
Revises: 003_backfill_signing_key_ciphertext
Create Date: 2026-04-05
"""

from __future__ import annotations

import base64
import os

from alembic import op
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import sqlalchemy as sa


revision = "004_drop_plaintext_signing_key"
down_revision = "003_backfill_key_ciphertext"
branch_labels = None
depends_on = None


def _decode_kek() -> bytes:
    raw = os.getenv("IDENTITY_KEY_ENCRYPTION_KEY_B64", "").strip()
    if not raw:
        raise RuntimeError(
            "IDENTITY_KEY_ENCRYPTION_KEY_B64 is required to downgrade signing keys."
        )
    padding = "=" * (-len(raw) % 4)
    decoded = base64.urlsafe_b64decode(f"{raw}{padding}")
    if len(decoded) != 32:
        raise RuntimeError(
            "IDENTITY_KEY_ENCRYPTION_KEY_B64 must decode to exactly 32 bytes."
        )
    return decoded


def _decrypt(ciphertext_b64: str, *, kid: str, key_bytes: bytes) -> str:
    blob = base64.urlsafe_b64decode(
        f"{ciphertext_b64}{'=' * (-len(ciphertext_b64) % 4)}"
    )
    if len(blob) < 13:
        raise RuntimeError("Signing key ciphertext is invalid during downgrade.")
    nonce, ciphertext = blob[:12], blob[12:]
    plaintext = AESGCM(key_bytes).decrypt(nonce, ciphertext, kid.encode("utf-8"))
    return plaintext.decode("utf-8")


def upgrade() -> None:
    with op.batch_alter_table("identity_signing_keys", recreate="always") as batch:
        batch.alter_column(
            "private_key_ciphertext_b64",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch.alter_column(
            "private_key_kek_version",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch.drop_column("private_key_pem")


def downgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "identity_signing_keys", sa.Column("private_key_pem", sa.Text(), nullable=True)
    )

    key_bytes = _decode_kek()
    rows = (
        bind.execute(
            sa.text(
                """
                SELECT kid, private_key_ciphertext_b64
                FROM identity_signing_keys
                """
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        ciphertext = str(row["private_key_ciphertext_b64"] or "").strip()
        if not ciphertext:
            raise RuntimeError("Signing key ciphertext is missing during downgrade.")
        private_key_pem = _decrypt(ciphertext, kid=str(row["kid"]), key_bytes=key_bytes)
        bind.execute(
            sa.text(
                """
                UPDATE identity_signing_keys
                SET private_key_pem = :private_key_pem
                WHERE kid = :kid
                """
            ),
            {"kid": row["kid"], "private_key_pem": private_key_pem},
        )

    missing = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM identity_signing_keys
            WHERE private_key_pem IS NULL
            """
        )
    ).scalar_one()
    if int(missing or 0) != 0:
        raise RuntimeError("Signing key downgrade did not restore every plaintext PEM.")

    with op.batch_alter_table("identity_signing_keys", recreate="always") as batch:
        batch.alter_column("private_key_pem", existing_type=sa.Text(), nullable=False)
        batch.alter_column(
            "private_key_ciphertext_b64",
            existing_type=sa.Text(),
            nullable=True,
        )
        batch.alter_column(
            "private_key_kek_version",
            existing_type=sa.String(length=64),
            nullable=True,
        )
