"""GATE-1 verification tests: GREEN on intact, RED on every tamper case.

The four mandated tamper cases are table-driven:
  1. flip one byte in a capture body
  2. edit a number inside facts.json
  3. swap two manifest entries
  4. corrupt the signature

Plus additional robustness cases (edit merkle root, edit a leaf hash, edit a
header in the manifest, delete a capture body) so coverage isn't limited to
the four headline cases. Every tamper case asserts:
  - verify_packet().ok is False
  - a non-None broken_node is reported (the verifier names the failure)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amber.packet import (
    CAPTURES_DIR,
    FACTS_FILE,
    MANIFEST_FILE,
    MERKLE_FILE,
    SIGNATURE_FILE,
    verify_packet,
)

from .conftest import read_json, write_json_canonical


def test_intact_packet_verifies_green(sealed_packet):
    """A freshly sealed packet verifies GREEN with no broken node."""
    result = verify_packet(sealed_packet["dir"])
    assert result.ok is True
    assert result.broken_node is None
    # Every recorded check passed.
    assert all(ok for _, ok, _ in result.checks)


def test_intact_packet_green_repeated(sealed_packet):
    """Determinism: verifying the same intact packet many times is always GREEN.

    (Satisfies the GATE-1 '100/100 GREEN on the intact packet' requirement
    without re-sealing — re-verification is the operation under test.)
    """
    pkt = sealed_packet["dir"]
    for _ in range(100):
        assert verify_packet(pkt).ok is True


# --------------------------------------------------------------------------- #
# Tamper mutators — each takes the packet dir and corrupts exactly one thing.
# --------------------------------------------------------------------------- #


def _flip_byte_in_capture(pkt: Path) -> str:
    """(1) Flip a single byte in a capture body."""
    body_path = pkt / CAPTURES_DIR / "de-01.body"
    data = bytearray(body_path.read_bytes())
    data[10] ^= 0x01  # flip one bit of one byte
    body_path.write_bytes(bytes(data))
    return "de-01"  # expected broken node


def _edit_number_in_facts(pkt: Path) -> str:
    """(2) Edit a number inside facts.json (the demo's headline tamper)."""
    facts = read_json(pkt / FACTS_FILE)
    facts["per_geo"][0]["price_gross"] = "9.99"  # change DE price 129.99 -> 9.99
    write_json_canonical(pkt / FACTS_FILE, facts)
    return FACTS_FILE


def _swap_manifest_entries(pkt: Path) -> str:
    """(3) Swap two manifest entries (reorder the captures list)."""
    manifest = read_json(pkt / MANIFEST_FILE)
    manifest["captures"][0], manifest["captures"][1] = (
        manifest["captures"][1],
        manifest["captures"][0],
    )
    write_json_canonical(pkt / MANIFEST_FILE, manifest)
    return MANIFEST_FILE


def _corrupt_signature(pkt: Path) -> str:
    """(4) Corrupt the ed25519 signature."""
    sig = read_json(pkt / SIGNATURE_FILE)
    sig_hex = sig["signature"]
    # Flip the first hex nibble to a different value -> invalid signature.
    flipped = ("f" if sig_hex[0] != "f" else "0") + sig_hex[1:]
    sig["signature"] = flipped
    write_json_canonical(pkt / SIGNATURE_FILE, sig)
    return SIGNATURE_FILE


def _edit_merkle_root(pkt: Path) -> str:
    """(robustness) Edit the recorded Merkle root."""
    doc = read_json(pkt / MERKLE_FILE)
    root = doc["root"]
    doc["root"] = ("0" if root[0] != "0" else "1") + root[1:]
    write_json_canonical(pkt / MERKLE_FILE, doc)
    return "merkle.json/root"


def _edit_leaf_hash(pkt: Path) -> str:
    """(robustness) Tamper a recorded leaf hash in merkle.json.

    The recomputed content leaf is still correct, so the verifier reports that
    the recorded leaf for that node disagrees with reality. leaves[0] is the
    first leaf in seal order = the first capture by capture_id ("be-01").
    """
    doc = read_json(pkt / MERKLE_FILE)
    first_label = doc["leaves"][0]["label"]
    lh = doc["leaves"][0]["leaf_hash"]
    doc["leaves"][0]["leaf_hash"] = ("0" if lh[0] != "0" else "1") + lh[1:]
    write_json_canonical(pkt / MERKLE_FILE, doc)
    return first_label


def _edit_manifest_header(pkt: Path) -> str:
    """(robustness) Edit a recorded header in the manifest."""
    manifest = read_json(pkt / MANIFEST_FILE)
    manifest["captures"][0]["headers"]["content-language"] = "xx-XX"
    write_json_canonical(pkt / MANIFEST_FILE, manifest)
    return MANIFEST_FILE


def _delete_capture_body(pkt: Path) -> str:
    """(robustness) Delete a capture body file referenced by the manifest."""
    (pkt / CAPTURES_DIR / "be-01.body").unlink()
    return "be-01"


def _swap_public_key(pkt: Path) -> str:
    """(robustness) Replace the public key with a different valid ed25519 key."""
    from amber.signer import generate_keypair

    sig = read_json(pkt / SIGNATURE_FILE)
    _, other_pub = generate_keypair()
    sig["public_key"] = other_pub
    write_json_canonical(pkt / SIGNATURE_FILE, sig)
    return SIGNATURE_FILE


TAMPER_CASES = [
    pytest.param(_flip_byte_in_capture, id="1-flip-byte-in-capture"),
    pytest.param(_edit_number_in_facts, id="2-edit-number-in-facts"),
    pytest.param(_swap_manifest_entries, id="3-swap-manifest-entries"),
    pytest.param(_corrupt_signature, id="4-corrupt-signature"),
    pytest.param(_edit_merkle_root, id="5-edit-merkle-root"),
    pytest.param(_edit_leaf_hash, id="6-edit-leaf-hash"),
    pytest.param(_edit_manifest_header, id="7-edit-manifest-header"),
    pytest.param(_delete_capture_body, id="8-delete-capture-body"),
    pytest.param(_swap_public_key, id="9-swap-public-key"),
]


@pytest.mark.parametrize("mutator", TAMPER_CASES)
def test_tamper_makes_packet_red(sealed_packet, mutator):
    """Every tamper case must turn the packet RED and name a broken node."""
    pkt = sealed_packet["dir"]
    # sanity: the packet is GREEN before tampering
    assert verify_packet(pkt).ok is True

    expected_node = mutator(pkt)

    result = verify_packet(pkt)
    assert result.ok is False, f"tamper {mutator.__name__} was NOT detected"
    assert result.broken_node is not None
    assert result.broken_node == expected_node, (
        f"expected broken_node {expected_node!r}, got {result.broken_node!r}"
    )


def test_revert_restores_green(sealed_packet):
    """THE TAMPER PROOF round-trip: GREEN -> edit -> RED -> revert -> GREEN."""
    pkt = sealed_packet["dir"]
    assert verify_packet(pkt).ok is True

    facts_path = pkt / FACTS_FILE
    original = facts_path.read_bytes()

    facts = json.loads(original.decode("utf-8"))
    facts["per_geo"][0]["price_gross"] = "9.99"
    write_json_canonical(facts_path, facts)
    assert verify_packet(pkt).ok is False

    facts_path.write_bytes(original)  # revert
    assert verify_packet(pkt).ok is True


def test_missing_file_is_red(sealed_packet):
    """A missing control file is reported, not crashed on."""
    pkt = sealed_packet["dir"]
    (pkt / SIGNATURE_FILE).unlink()
    result = verify_packet(pkt)
    assert result.ok is False
    assert result.broken_node == SIGNATURE_FILE


def test_invalid_json_is_red(sealed_packet):
    """A control file corrupted into invalid JSON is reported, not crashed on."""
    pkt = sealed_packet["dir"]
    (pkt / FACTS_FILE).write_bytes(b"{not valid json")
    result = verify_packet(pkt)
    assert result.ok is False
    assert result.broken_node is not None
