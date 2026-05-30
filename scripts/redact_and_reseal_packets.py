"""Redact embedded third-party API keys from committed capture bodies, then re-seal.

SECURITY FIX. The committed REAL MediaMarkt capture bodies embed MediaMarkt's OWN
client-side Google API keys (Maps / Firebase) inside the page's inline JSON config
blob — e.g. ``"googlePudoMapKey":"AIzaSy..."`` and ``"firebase":{"publicApiKey":
"AIzaSy..."}``. Those are someone else's keys; GitHub secret-scanning (correctly)
flags them. They are NOT a price, GTIN, currency, or any number Amber extracts:
every extracted fact lives in the already-deterministic, already-signed
``facts.json``, and the keys appear ONLY in the body HTML. So each key string can
be replaced with a fixed deterministic placeholder without changing a single
Amber fact.

Redacting a body changes its sha256 -> changes that capture's Merkle leaf ->
changes the root -> invalidates the signature, so ``verify_packet`` would go RED.
Therefore each affected packet must be RE-SEALED: recompute body hashes ->
rebuild the Merkle tree -> re-sign the root. This is done OFFLINE from the
EXISTING committed bodies + manifests (NOT re-captured -- re-capturing would
re-introduce live keys and change every fact), reusing the exact production seal
machinery (``amber.packet.seal_packet``), and re-signed with the EXISTING demo
signing key so the signer public key is unchanged (``f2de2b5f...``). ``facts.json``
is preserved exactly (it is already canonical and contains no keys), so no
price / GTIN / currency / fact changes.

Run::

    python scripts/redact_and_reseal_packets.py
    verify_packet samples/live_packet --pubkey f2de2b5f14785372ced46288f3009448db17495312fe0492377fd14b036a5dc8
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from amber.packet import CAPTURES_DIR, CaptureInput, seal_packet  # noqa: E402
from amber.signer import public_key_for  # noqa: E402

KEY_PATH = REPO / "amber" / "keys" / "demo-signer.key"
EXPECTED_PUBKEY = "f2de2b5f14785372ced46288f3009448db17495312fe0492377fd14b036a5dc8"

# The 5 packets that hold REAL captured MediaMarkt bodies with embedded keys.
PACKETS = [
    REPO / "samples" / "live_packet",
    REPO / "samples" / "temporal" / "cap-01",
    REPO / "samples" / "temporal" / "cap-02",
    REPO / "samples" / "temporal" / "cap-03",
    REPO / "samples" / "temporal" / "cap-04",
]

# A live Google API key is "AIzaSy" + 33 url-safe-base64 chars. We match a tail of
# >=30 to catch any embedded key robustly. The fixed placeholder below is chosen
# so it never matches this live-key shape on a re-run (its tail differs in length
# AND it contains "_REDACTED_"), so redaction is idempotent.
LIVE_KEY_RE = re.compile(rb"AIzaSy[A-Za-z0-9_\-]{30,}")
# Fixed deterministic placeholder (tail length 36 != a real key's 33).
PLACEHOLDER = b"AIzaSy_REDACTED_THIRD_PARTY_KEY_0000000000"


def load_signing_key() -> str:
    """Load the EXISTING demo signer PRIVATE key (env or gitignored file).

    Never generates a new key. Verifies the loaded key derives to the pinned
    public key before use, so a wrong key fails loudly instead of silently
    re-sealing packets under a new (untrusted) signer.
    """
    env = os.environ.get("AMBER_SIGNING_KEY", "").strip()
    key = env or (KEY_PATH.read_text(encoding="ascii").strip() if KEY_PATH.exists() else "")
    if not key:
        raise SystemExit(
            "No signing key found. Set AMBER_SIGNING_KEY=<64-hex-seed> or place the "
            f"existing demo key at {KEY_PATH} (gitignored). DO NOT generate a new key."
        )
    derived = public_key_for(key)
    if derived != EXPECTED_PUBKEY:
        raise SystemExit(
            f"Loaded signing key derives to {derived[:16]}..., not the pinned demo "
            f"signer {EXPECTED_PUBKEY[:16]}...; refusing to re-seal with a wrong key. "
            "(No new key was generated.)"
        )
    return key


def redact_body(raw: bytes) -> tuple[bytes, int]:
    """Replace every live-looking Google API key with the fixed placeholder.

    Returns (redacted_bytes, num_keys_replaced). The placeholder itself never
    matches the live-key pattern, so re-running this is idempotent.
    """
    count = 0

    def _sub(_m: "re.Match[bytes]") -> bytes:
        nonlocal count
        count += 1
        return PLACEHOLDER

    return LIVE_KEY_RE.sub(_sub, raw), count


def reseal_packet(packet: Path, private_key_hex: str) -> tuple[int, int]:
    """Redact every body in ``packet`` and re-seal it.

    Returns (#bodies_changed, #key_occurrences_redacted).
    """
    facts = json.loads((packet / "facts.json").read_text(encoding="utf-8"))
    manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))

    pairs: list[tuple[CaptureInput, bytes]] = []
    bodies_changed = 0
    keys_redacted = 0
    for entry in manifest["captures"]:
        cap = CaptureInput(
            capture_id=entry["capture_id"],
            url=entry["url"],
            country=entry["country"],
            exit_ip=entry["exit_ip"],
            requested_at=entry["requested_at"],
            http_status=int(entry["http_status"]),
            headers=dict(entry.get("headers", {})),
        )
        body_path = packet / CAPTURES_DIR / f"{cap.capture_id}.body"
        original = body_path.read_bytes()
        redacted, n = redact_body(original)
        if redacted != original:
            bodies_changed += 1
            keys_redacted += n
        # seal_packet rewrites the body too, but pass the redacted bytes so the
        # Merkle leaf is computed over redacted content.
        pairs.append((cap, redacted))

    # facts.json is preserved exactly: seal_packet writes canonical_json(facts),
    # which (verified offline) equals the existing committed bytes -- no fact,
    # price, GTIN, or currency changes. Only the capture-body leaves move, because
    # only the bodies were redacted. Re-signed with the EXISTING demo key.
    seal_packet(packet, pairs, facts, private_key_hex)
    return bodies_changed, keys_redacted


def main() -> int:
    private_key_hex = load_signing_key()
    total_bodies = 0
    total_keys = 0
    for packet in PACKETS:
        b, k = reseal_packet(packet, private_key_hex)
        total_bodies += b
        total_keys += k
        print(f"Re-sealed {packet.relative_to(REPO)}: {b} bodies redacted, {k} key occurrences replaced.")
    print(
        f"\nDone. {total_keys} key occurrences redacted across {total_bodies} bodies "
        f"in {len(PACKETS)} packets. Signer pubkey unchanged ({EXPECTED_PUBKEY[:16]}...)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
