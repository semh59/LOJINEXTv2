"""Password and secret hashing helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000


def hash_secret(secret: str) -> str:
    """Hash a password or client secret."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    )
    return f"{_ALGORITHM}${_ITERATIONS}${salt}${digest.hex()}"


def verify_secret(secret: str, encoded: str) -> bool:
    """Verify a password or client secret against its encoded hash."""
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = encoded.split("$", 3)
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    iterations = int(iterations_raw)
    candidate = hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), bytes.fromhex(salt_hex), iterations
    )
    return hmac.compare_digest(candidate.hex(), digest_hex)
