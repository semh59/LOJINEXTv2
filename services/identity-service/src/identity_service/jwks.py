"""RSA key generation and JWKS helpers."""

from __future__ import annotations

import json

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_keypair() -> tuple[str, str]:
    """Return a PEM-encoded RSA private/public key pair."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def public_key_to_jwk(public_key_pem: str, kid: str, algorithm: str) -> dict[str, object]:
    """Convert a PEM public key into a JWK document."""
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = kid
    jwk["use"] = "sig"
    jwk["alg"] = algorithm
    return jwk
