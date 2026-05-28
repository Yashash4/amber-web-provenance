"""ed25519 signature verification.

Lifted from Reef's ``reef/control-plane/atlas/app/crypto/verifier.py``. Returns
a boolean verdict and never raises — the caller (``verify_packet``) wants a
clean true/false so it can report exactly which node of the chain of custody
broke, rather than crashing on a malformed signature blob a tamperer supplied.
"""

from __future__ import annotations

from typing import Any

from cryptography.exceptions import InvalidSignature

from amber.signer import canonical_json, load_public_key


def verify_bytes_signature(
    message: bytes,
    signature_hex: str,
    public_key_hex: str,
) -> bool:
    """Verify an ed25519 signature over raw ``message`` bytes.

    True on a good signature; False on any mismatch (bad signature bytes, wrong
    key, tampered payload). Never raises.
    """
    try:
        sig_bytes = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    try:
        pk = load_public_key(public_key_hex)
    except ValueError:
        return False
    try:
        pk.verify(sig_bytes, message)
    except InvalidSignature:
        return False
    except Exception:
        # Any other crypto-layer surprise = treat as a verification failure.
        return False
    return True


def verify_root_signature(
    root_hex: str,
    signature_hex: str,
    public_key_hex: str,
) -> bool:
    """Verify an ed25519 signature over the raw bytes of the Merkle root."""
    try:
        root_bytes = bytes.fromhex(root_hex)
    except ValueError:
        return False
    return verify_bytes_signature(root_bytes, signature_hex, public_key_hex)


def verify_manifest_signature(
    manifest_dict: dict[str, Any],
    signature_hex: str,
    public_key_hex: str,
) -> bool:
    """Verify an ed25519 signature over canonical-JSON(manifest_dict)."""
    return verify_bytes_signature(
        canonical_json(manifest_dict), signature_hex, public_key_hex
    )
