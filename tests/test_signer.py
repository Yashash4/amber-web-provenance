"""ed25519 signer/verifier tests (lifted from Reef, adapted to sign the root)."""

from __future__ import annotations

from amber.signer import (
    canonical_json,
    generate_keypair,
    public_key_for,
    sign_bytes,
    sign_root,
)
from amber.verifier import (
    verify_bytes_signature,
    verify_manifest_signature,
    verify_root_signature,
)


def test_keypair_is_32_byte_hex():
    sk, pk = generate_keypair()
    assert len(sk) == 64 and len(pk) == 64
    assert bytes.fromhex(sk) and bytes.fromhex(pk)


def test_public_key_for_matches_generated():
    sk, pk = generate_keypair()
    assert public_key_for(sk) == pk


def test_sign_and_verify_root_roundtrip():
    sk, pk = generate_keypair()
    root_hex = "ab" * 32  # a plausible 32-byte root
    sig = sign_root(root_hex, sk)
    assert verify_root_signature(root_hex, sig, pk) is True


def test_wrong_root_fails():
    sk, pk = generate_keypair()
    sig = sign_root("ab" * 32, sk)
    assert verify_root_signature("cd" * 32, sig, pk) is False


def test_wrong_key_fails():
    sk, _ = generate_keypair()
    _, other_pub = generate_keypair()
    sig = sign_root("ab" * 32, sk)
    assert verify_root_signature("ab" * 32, sig, other_pub) is False


def test_corrupt_signature_returns_false_not_raises():
    sk, pk = generate_keypair()
    sign_root("ab" * 32, sk)
    # garbage signature, garbage key — must return False, never raise
    assert verify_root_signature("ab" * 32, "zz", pk) is False
    assert verify_root_signature("ab" * 32, "00" * 64, "not-hex") is False


def test_canonical_json_is_order_independent():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b == b'{"a":2,"b":1}'


def test_canonical_json_preserves_unicode():
    assert canonical_json({"price": "129,99 €"}) == '{"price":"129,99 €"}'.encode()


def test_manifest_signature_roundtrip():
    sk, pk = generate_keypair()
    manifest = {"captures": [{"id": "x"}]}
    sig = sign_bytes(canonical_json(manifest), sk)
    assert verify_manifest_signature(manifest, sig, pk) is True
    manifest["captures"][0]["id"] = "y"
    assert verify_manifest_signature(manifest, sig, pk) is False


def test_verify_bytes_signature_roundtrip():
    sk, pk = generate_keypair()
    msg = b"some raw bytes"
    sig = sign_bytes(msg, sk)
    assert verify_bytes_signature(msg, sig, pk) is True
    assert verify_bytes_signature(b"other", sig, pk) is False
