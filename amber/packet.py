"""The Amber evidence packet: seal + verify.

An Amber packet is a directory of REAL captured bytes plus signed manifests —
no WARC, no external anchor (those are Phase 2). The layout is::

    amber_packet/
      captures/<capture_id>.body   raw bytes of each fetched response
      manifest.json                per-capture metadata + sha256(body)
      facts.json                   Layer-1 DETERMINISTIC facts (no LLM)
      merkle.json                  ordered leaf hashes + the Merkle root
      signature.json               ed25519 signature over the Merkle root + pubkey

The Merkle leaves, in a fixed deterministic order, are:

    1. sha256-leaf of each capture body, ordered by capture_id
    2. sha256-leaf of the canonical bytes of manifest.json
    3. sha256-leaf of the canonical bytes of facts.json

Because ``facts.json`` is itself a leaf, editing any number in it changes its
leaf hash → changes the root → the signature over the root no longer verifies
→ ``verify_packet`` reports RED. The same holds for flipping any byte of any
capture body, and for reordering manifest entries (which changes the canonical
manifest bytes). That property is THE TAMPER PROOF the demo turns on, so it is
enforced by table-driven tests, not asserted.

Layer-2 (the AI legal label) is NEVER written into this packet — the signed
bundle contains only Layer-1 facts + raw captures. (See docs/01-PROJECT.md.)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from amber import merkle
from amber.signer import canonical_json, public_key_for, sign_root
from amber.verifier import verify_root_signature

CAPTURES_DIR = "captures"
MANIFEST_FILE = "manifest.json"
FACTS_FILE = "facts.json"
MERKLE_FILE = "merkle.json"
SIGNATURE_FILE = "signature.json"

CAPTURE_SUFFIX = ".body"

# Stable leaf labels recorded in merkle.json so verify can name the broken node.
LEAF_MANIFEST = "manifest.json"
LEAF_FACTS = "facts.json"


def sha256_hex(data: bytes) -> str:
    """Hex SHA-256 of raw bytes (the body content hash recorded in the manifest)."""
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Sealing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CaptureInput:
    """One captured response to be sealed into the packet.

    ``body`` is the exact raw bytes that were fetched. Everything else is the
    deterministic, observed metadata about that fetch. No field may be derived
    by an LLM — these are Layer-1 facts.
    """

    capture_id: str
    url: str
    country: str
    exit_ip: str
    requested_at: str  # ISO-8601, same-second across a batch
    http_status: int
    headers: dict[str, str]  # selected response headers (geo signals)


def _manifest_entry(cap: CaptureInput, body: bytes) -> dict[str, Any]:
    return {
        "capture_id": cap.capture_id,
        "url": cap.url,
        "country": cap.country,
        "exit_ip": cap.exit_ip,
        "requested_at": cap.requested_at,
        "http_status": cap.http_status,
        "sha256_body": sha256_hex(body),
        "headers": dict(cap.headers),
    }


def build_manifest(captures: list[tuple[CaptureInput, bytes]]) -> dict[str, Any]:
    """Build the manifest dict from (capture, body) pairs.

    Entries are sorted by ``capture_id`` so the serialised manifest is
    deterministic; reordering the input cannot change the sealed bytes, and a
    tamperer who swaps two entries in the written file changes the canonical
    bytes and is caught.
    """
    seen: set[str] = set()
    entries = []
    for cap, body in captures:
        if cap.capture_id in seen:
            raise ValueError(f"duplicate capture_id: {cap.capture_id!r}")
        seen.add(cap.capture_id)
        entries.append(_manifest_entry(cap, body))
    entries.sort(key=lambda e: e["capture_id"])
    return {"schema": "amber/manifest@1", "captures": entries}


def _ordered_leaves(
    captures: list[tuple[CaptureInput, bytes]],
    manifest: dict[str, Any],
    facts: dict[str, Any],
) -> list[tuple[str, bytes]]:
    """Return the ordered (label, leaf_hash_bytes) list the root commits to.

    Order: each capture body (by capture_id), then manifest, then facts.
    """
    leaves: list[tuple[str, bytes]] = []
    for cap, body in sorted(captures, key=lambda cb: cb[0].capture_id):
        leaves.append((cap.capture_id, merkle.leaf_hash(body)))
    leaves.append((LEAF_MANIFEST, merkle.leaf_hash(canonical_json(manifest))))
    leaves.append((LEAF_FACTS, merkle.leaf_hash(canonical_json(facts))))
    return leaves


def seal_packet(
    out_dir: str | Path,
    captures: list[tuple[CaptureInput, bytes]],
    facts: dict[str, Any],
    private_key_hex: str,
) -> Path:
    """Seal a packet into ``out_dir`` and return its path.

    Writes captures/, manifest.json, facts.json, merkle.json, signature.json.
    The Merkle root is ed25519-signed over its raw bytes; the public key is
    embedded in signature.json so the packet is self-verifying offline.
    """
    if not captures:
        raise ValueError("seal_packet: at least one capture is required")

    out = Path(out_dir)
    captures_path = out / CAPTURES_DIR
    captures_path.mkdir(parents=True, exist_ok=True)

    # Write the raw capture bodies exactly as captured.
    for cap, body in captures:
        (captures_path / f"{cap.capture_id}{CAPTURE_SUFFIX}").write_bytes(body)

    manifest = build_manifest(captures)
    (out / MANIFEST_FILE).write_bytes(canonical_json(manifest))
    (out / FACTS_FILE).write_bytes(canonical_json(facts))

    ordered = _ordered_leaves(captures, manifest, facts)
    root_hex = merkle.merkle_root([h for _, h in ordered]).hex()

    merkle_doc = {
        "schema": "amber/merkle@1",
        "hash_algorithm": "sha256",
        "tree": "rfc6962-domain-separated",
        "leaves": [
            {"label": label, "leaf_hash": h.hex()} for label, h in ordered
        ],
        "root": root_hex,
    }
    (out / MERKLE_FILE).write_bytes(canonical_json(merkle_doc))

    signature_hex = sign_root(root_hex, private_key_hex)
    signature_doc = {
        "schema": "amber/signature@1",
        "algorithm": "ed25519",
        "signed_over": "merkle_root_raw_bytes",
        "public_key": public_key_for(private_key_hex),
        "signature": signature_hex,
    }
    (out / SIGNATURE_FILE).write_bytes(canonical_json(signature_doc))

    return out


# --------------------------------------------------------------------------- #
# Verifying
# --------------------------------------------------------------------------- #


@dataclass
class VerifyResult:
    """Outcome of verifying a packet.

    ``ok`` is the verdict. ``broken_node`` names the first link in the chain of
    custody that failed (a capture_id, "manifest.json", "facts.json",
    "merkle.json/root", or "signature.json"). ``checks`` is the full ordered
    audit trail for the report.
    """

    ok: bool
    broken_node: str | None
    detail: str
    checks: list[tuple[str, bool, str]]


def _fail(checks: list, node: str, detail: str) -> VerifyResult:
    checks.append((node, False, detail))
    return VerifyResult(ok=False, broken_node=node, detail=detail, checks=checks)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_bytes().decode("utf-8"))


def verify_packet(packet_dir: str | Path) -> VerifyResult:
    """Re-verify a sealed packet, fully offline.

    Recomputes every capture body hash against the manifest, rebuilds every
    Merkle leaf and the root, and verifies the ed25519 signature over the root.
    Returns a :class:`VerifyResult`; never raises on a tampered/missing file —
    it reports which node broke.
    """
    checks: list[tuple[str, bool, str]] = []
    pkt = Path(packet_dir)

    # 0. Required files present.
    for name in (MANIFEST_FILE, FACTS_FILE, MERKLE_FILE, SIGNATURE_FILE):
        if not (pkt / name).exists():
            return _fail(checks, name, f"missing required file: {name}")
    if not (pkt / CAPTURES_DIR).is_dir():
        return _fail(checks, CAPTURES_DIR, "missing captures/ directory")

    # 1. Parse the four control files (a tamperer may produce invalid JSON).
    try:
        manifest = _load_json(pkt / MANIFEST_FILE)
        facts = _load_json(pkt / FACTS_FILE)
        merkle_doc = _load_json(pkt / MERKLE_FILE)
        signature_doc = _load_json(pkt / SIGNATURE_FILE)
    except (ValueError, UnicodeDecodeError) as exc:
        return _fail(checks, "json", f"could not parse a control file as JSON: {exc}")

    entries = manifest.get("captures")
    if not isinstance(entries, list) or not entries:
        return _fail(checks, MANIFEST_FILE, "manifest has no captures list")

    # 2. Recompute every capture body hash vs the manifest, and rebuild the
    #    capture leaves in the manifest's (capture_id-sorted) order.
    capture_leaves: list[tuple[str, bytes]] = []
    for entry in sorted(entries, key=lambda e: str(e.get("capture_id", ""))):
        cid = entry.get("capture_id")
        if not isinstance(cid, str) or not cid:
            return _fail(checks, MANIFEST_FILE, "a manifest entry has no capture_id")
        body_path = pkt / CAPTURES_DIR / f"{cid}{CAPTURE_SUFFIX}"
        if not body_path.exists():
            return _fail(checks, cid, f"capture body file missing for {cid}")
        body = body_path.read_bytes()
        recomputed = sha256_hex(body)
        if recomputed != entry.get("sha256_body"):
            return _fail(
                checks,
                cid,
                f"capture body hash mismatch: recomputed {recomputed} "
                f"!= manifest {entry.get('sha256_body')}",
            )
        checks.append((cid, True, f"body sha256 ok ({recomputed[:16]}...)"))
        capture_leaves.append((cid, merkle.leaf_hash(body)))

    # 3. Rebuild the ordered leaf set exactly as seal_packet did and recompute
    #    the root. Using canonical_json(manifest)/canonical_json(facts) means
    #    any edit to those files changes their leaf and therefore the root.
    ordered: list[tuple[str, bytes]] = list(capture_leaves)
    ordered.append((LEAF_MANIFEST, merkle.leaf_hash(canonical_json(manifest))))
    ordered.append((LEAF_FACTS, merkle.leaf_hash(canonical_json(facts))))

    # 3a. Cross-check our rebuilt leaves against the leaf list recorded in
    #     merkle.json (catches a tamperer who edits merkle.json's leaf table).
    recorded = merkle_doc.get("leaves")
    if not isinstance(recorded, list) or len(recorded) != len(ordered):
        return _fail(
            checks,
            MERKLE_FILE,
            f"merkle.json leaf count {len(recorded) if isinstance(recorded, list) else 'n/a'} "
            f"!= recomputed {len(ordered)}",
        )
    for (label, leaf_h), rec in zip(ordered, recorded, strict=True):
        if rec.get("label") != label:
            # The recorded leaf TABLE itself was reordered/relabelled in
            # merkle.json — point at the merkle file.
            return _fail(
                checks,
                f"{MERKLE_FILE}/{rec.get('label')}",
                f"merkle.json leaf order changed: expected {label!r} "
                f"at this position, found {rec.get('label')!r}",
            )
        if rec.get("leaf_hash") != leaf_h.hex():
            # The recomputed leaf differs from what was sealed: the underlying
            # CONTENT changed. Name the content node (facts.json / manifest.json
            # / the capture_id) — that is the forensically meaningful answer and
            # the message the tamper-proof demo shows ("broken at: facts.json").
            return _fail(
                checks,
                label,
                f"content of {label!r} changed since sealing: recomputed leaf "
                f"{leaf_h.hex()} != sealed leaf {rec.get('leaf_hash')}",
            )
    checks.append((MERKLE_FILE, True, "leaf table matches recomputed leaves"))

    recomputed_root = merkle.merkle_root([h for _, h in ordered]).hex()
    recorded_root = merkle_doc.get("root")
    if recomputed_root != recorded_root:
        return _fail(
            checks,
            "merkle.json/root",
            f"Merkle root mismatch: recomputed {recomputed_root} != recorded {recorded_root}",
        )
    checks.append(("merkle.json/root", True, f"root ok ({recomputed_root[:16]}...)"))

    # 4. Verify the ed25519 signature over the recomputed root. We sign the
    #    RECOMPUTED root (not the recorded one) so a tamperer cannot rescue a
    #    bad packet by also editing merkle.json's root field.
    public_key = signature_doc.get("public_key")
    signature_hex = signature_doc.get("signature")
    if not isinstance(public_key, str) or not isinstance(signature_hex, str):
        return _fail(checks, SIGNATURE_FILE, "signature.json missing public_key/signature")
    if not verify_root_signature(recomputed_root, signature_hex, public_key):
        return _fail(
            checks,
            SIGNATURE_FILE,
            "ed25519 signature does not verify over the recomputed Merkle root",
        )
    checks.append((SIGNATURE_FILE, True, "ed25519 signature verified over root"))

    return VerifyResult(ok=True, broken_node=None, detail="all checks passed", checks=checks)
