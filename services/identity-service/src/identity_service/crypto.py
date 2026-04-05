"""Encryption helpers for persisted signing keys."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def require_kek_bytes() -> bytes:
    """Return the configured key-encryption key bytes."""
    raw = os.getenv("IDENTITY_KEY_ENCRYPTION_KEY_B64", "").strip()
    if not raw:
        raise ValueError("IDENTITY_KEY_ENCRYPTION_KEY_B64 is required.")
    key = _decode_base64(raw)
    if len(key) != 32:
        raise ValueError(
            "IDENTITY_KEY_ENCRYPTION_KEY_B64 must decode to exactly 32 bytes."
        )
    return key


def require_kek_version() -> str:
    """Return the configured KEK version string."""
    version = os.getenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", "").strip()
    if not version:
        raise ValueError("IDENTITY_KEY_ENCRYPTION_KEY_VERSION is required.")
    return version


def encrypt_private_key(private_key_pem: str, *, aad: str) -> str:
    """Encrypt a PEM string with the configured KEK."""
    key = require_kek_bytes()
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(
        nonce, private_key_pem.encode("utf-8"), aad.encode("utf-8")
    )
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_private_key(ciphertext_b64: str, *, aad: str) -> str:
    """Decrypt a stored PEM ciphertext with the configured KEK."""
    blob = _decode_base64(ciphertext_b64.strip())
    if len(blob) < 13:
        raise ValueError("Signing key ciphertext is invalid.")
    nonce, ciphertext = blob[:12], blob[12:]
    plaintext = AESGCM(require_kek_bytes()).decrypt(
        nonce, ciphertext, aad.encode("utf-8")
    )
    return plaintext.decode("utf-8")
