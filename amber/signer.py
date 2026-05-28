"""ed25519 key generation and signing.

Lifted from Reef's ``reef/control-plane/atlas/app/crypto/signer.py`` and
adapted for Amber: Reef signed a canonical-JSON manifest; Amber signs the raw
32-byte Merkle ROOT (``sign_root``) so the signature transitively commits to
every capture body + ``manifest.json`` + ``facts.json`` that are leaves of the
tree. The canonical-JSON helper is retained because ``signature.json`` and the
manifest are themselves serialised canonically.

Keys are raw 32-byte seeds encoded as 64-char hex strings — never PEM/DER
blobs — matching Reef's convention so the two verifiers are interchangeable.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json(payload: Any) -> bytes:
    """Return a deterministic byte serialisation suitable for hashing/signing.

    JSON with sorted keys + compact separators + no ASCII escaping of non-ASCII
    characters (so a "€" price renders as one UTF-8 sequence, not ``\\u20ac``).
    Mirrors Sigstore + JWS-RFC8785 canonical signing payloads — and Reef's
    ``signer.py`` — so the byte sequence is reproducible regardless of dict
    insertion order.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,  # reject NaN/Infinity: not valid RFC 8259 JSON, not signable
    ).encode("utf-8")


def fingerprint(public_key_hex: str) -> str:
    """Return the first 16 hex chars of sha256(pubkey) as a short fingerprint."""
    return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()[:16]


def generate_keypair() -> tuple[str, str]:
    """Generate a fresh ed25519 keypair.

    Returns ``(private_key_hex, public_key_hex)`` — both 64-char (32-byte) hex
    strings. The private key bytes are the raw seed.
    """
    sk = Ed25519PrivateKey.generate()
    sk_bytes = sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pk = sk.public_key()
    pk_bytes = pk.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sk_bytes.hex(), pk_bytes.hex()


def _load_private_key(private_key_hex: str) -> Ed25519PrivateKey:
    sk_bytes = bytes.fromhex(private_key_hex)
    if len(sk_bytes) != 32:
        raise ValueError(
            f"ed25519 private key must be 32 raw bytes (got {len(sk_bytes)})"
        )
    return Ed25519PrivateKey.from_private_bytes(sk_bytes)


def load_public_key(public_key_hex: str) -> Ed25519PublicKey:
    """Build an Ed25519PublicKey from a 32-byte hex pubkey."""
    pk_bytes = bytes.fromhex(public_key_hex)
    if len(pk_bytes) != 32:
        raise ValueError(
            f"ed25519 public key must be 32 raw bytes (got {len(pk_bytes)})"
        )
    return Ed25519PublicKey.from_public_bytes(pk_bytes)


def public_key_for(private_key_hex: str) -> str:
    """Derive the hex public key for a given hex private key."""
    pk = _load_private_key(private_key_hex).public_key()
    return pk.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def sign_bytes(message: bytes, private_key_hex: str) -> str:
    """ed25519-sign arbitrary bytes. Returns the hex-encoded 64-byte signature."""
    sk = _load_private_key(private_key_hex)
    return sk.sign(message).hex()


def sign_root(root_hex: str, private_key_hex: str) -> str:
    """ed25519-sign the Merkle root.

    The root is signed over its raw bytes (``bytes.fromhex(root_hex)``), not
    its hex text — so the signature commits to the actual 32-byte digest.
    """
    return sign_bytes(bytes.fromhex(root_hex), private_key_hex)


def sign_manifest(manifest_dict: dict[str, Any], private_key_hex: str) -> str:
    """Sign a dict over its canonical-JSON serialisation (Reef-compatible)."""
    return sign_bytes(canonical_json(manifest_dict), private_key_hex)
