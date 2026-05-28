"""Verify the committed REAL packet (built from a real HTTP GET) is GREEN.

This is the test-suite mirror of GATE 1: the packet in samples/real_packet was
sealed from genuinely-fetched bytes (scripts/build_real_packet.py), and it must
verify GREEN offline. Also exercises the CLI entry point's exit codes.

Skipped (not failed) if the real packet hasn't been built yet, so a fresh clone
can run the rest of the suite before fetching.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amber.cli import main as verify_cli_main
from amber.packet import FACTS_FILE, verify_packet

REPO = Path(__file__).resolve().parent.parent
REAL_PACKET = REPO / "samples" / "real_packet"

needs_real_packet = pytest.mark.skipif(
    not REAL_PACKET.is_dir(),
    reason="samples/real_packet not built; run scripts/build_real_packet.py",
)


@needs_real_packet
def test_real_packet_verifies_green():
    result = verify_packet(REAL_PACKET)
    assert result.ok is True
    assert result.broken_node is None


@needs_real_packet
def test_real_packet_cli_exit_zero():
    assert verify_cli_main([str(REAL_PACKET)]) == 0


@needs_real_packet
def test_real_packet_cli_exit_nonzero_after_tamper(tmp_path):
    """Copy the real packet, tamper facts.json, confirm the CLI exits non-zero."""
    import shutil

    from .conftest import read_json, write_json_canonical

    copied = tmp_path / "real_packet"
    shutil.copytree(REAL_PACKET, copied)
    assert verify_cli_main([str(copied)]) == 0

    facts = read_json(copied / FACTS_FILE)
    facts["observations"][0]["body_bytes"] = 0
    write_json_canonical(copied / FACTS_FILE, facts)

    assert verify_cli_main([str(copied)]) == 1


@needs_real_packet
def test_real_packet_cli_key_substitution_forge_exits_nonzero(tmp_path):
    """End-to-end via the CLI on the GOLDEN packet: a key-substitution forge
    (edit a fact + recompute the root + re-sign with a FRESH key + embed the new
    pubkey) must exit non-zero (RED) because the forged key is not in the
    committed trusted allowlist."""
    import shutil

    from amber import merkle
    from amber.packet import (
        CAPTURES_DIR,
        LEAF_FACTS,
        LEAF_MANIFEST,
        MANIFEST_FILE,
        MERKLE_FILE,
        SIGNATURE_FILE,
    )
    from amber.signer import canonical_json, generate_keypair, sign_root

    from .conftest import read_json, write_json_canonical

    copied = tmp_path / "real_packet"
    shutil.copytree(REAL_PACKET, copied)
    assert verify_cli_main([str(copied)]) == 0  # GREEN against committed allowlist

    facts = read_json(copied / FACTS_FILE)
    facts["observations"][0]["body_bytes"] = 0  # tamper a number
    write_json_canonical(copied / FACTS_FILE, facts)

    manifest = read_json(copied / MANIFEST_FILE)
    leaves = []
    for entry in sorted(manifest["captures"], key=lambda e: e["capture_id"]):
        body = (copied / CAPTURES_DIR / f"{entry['capture_id']}.body").read_bytes()
        leaves.append((entry["capture_id"], merkle.leaf_hash(body)))
    leaves.append((LEAF_MANIFEST, merkle.leaf_hash(canonical_json(manifest))))
    leaves.append((LEAF_FACTS, merkle.leaf_hash(canonical_json(facts))))
    new_root = merkle.merkle_root([h for _, h in leaves]).hex()
    merkle_doc = read_json(copied / MERKLE_FILE)
    merkle_doc["leaves"] = [{"label": label, "leaf_hash": h.hex()} for label, h in leaves]
    merkle_doc["root"] = new_root
    write_json_canonical(copied / MERKLE_FILE, merkle_doc)

    forge_sk, forge_pk = generate_keypair()
    sig = read_json(copied / SIGNATURE_FILE)
    sig["public_key"] = forge_pk
    sig["signature"] = sign_root(new_root, forge_sk)
    write_json_canonical(copied / SIGNATURE_FILE, sig)

    # CLI defaults to the committed allowlist, which does NOT contain forge_pk.
    assert verify_cli_main([str(copied)]) == 1


def test_cli_nonexistent_dir_exits_2():
    assert verify_cli_main(["/no/such/amber/packet/here"]) == 2
