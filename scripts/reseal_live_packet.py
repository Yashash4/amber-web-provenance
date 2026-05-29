"""Re-seal samples/live_packet to embed the deterministic dollarization fact.

The live packet was sealed before the Layer-1 dollarization bridge existed. The
REAL captured bytes (capture bodies) and every observed fact are unchanged; the
only addition is the deterministic, SIGNED ``business_impact`` block derived from
the already-present, already-signed ``cross_country_comparison.net_delta`` (a
pure multiplication by the buyer-supplied volume assumption — no LLM, no new
observation). Re-sealing simply puts that derived fact inside the Merkle-signed
bundle so it is tamper-protected.

This reconstructs the CaptureInputs from the committed manifest + the real body
files (so the capture leaves are byte-identical), recomputes facts.json = the
existing facts + the new ``business_impact``, and re-signs with the demo signer's
PRIVATE key (env ``AMBER_SIGNING_KEY`` or the gitignored
``amber/keys/demo-signer.key``). Verifying needs no secret.

Run::

    python scripts/reseal_live_packet.py
    verify_packet samples/live_packet --pubkey <demo pubkey>   # -> GREEN
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from amber.business import DEFAULT_ANNUAL_VOLUME_ASSUMPTION, dollarize_margin_leak  # noqa: E402
from amber.packet import CAPTURES_DIR, CaptureInput, seal_packet  # noqa: E402

PACKET = REPO / "samples" / "live_packet"
KEY_PATH = REPO / "amber" / "keys" / "demo-signer.key"


def load_signing_key() -> str:
    env = os.environ.get("AMBER_SIGNING_KEY", "").strip()
    if env:
        return env
    if KEY_PATH.exists():
        return KEY_PATH.read_text(encoding="ascii").strip()
    raise SystemExit(
        "No signing key found. Set AMBER_SIGNING_KEY=<64-hex-seed> or write it "
        f"to {KEY_PATH} (gitignored). Verifying needs no secret."
    )


def main() -> int:
    facts = json.loads((PACKET / "facts.json").read_text(encoding="utf-8"))
    manifest = json.loads((PACKET / "manifest.json").read_text(encoding="utf-8"))

    # Reconstruct the capture (input, body) pairs from the committed manifest +
    # the REAL body files, byte-for-byte (the capture leaves are unchanged).
    pairs: list[tuple[CaptureInput, bytes]] = []
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
        body = (PACKET / CAPTURES_DIR / f"{cap.capture_id}.body").read_bytes()
        pairs.append((cap, body))

    # The ONLY change to facts.json: add the deterministic dollarization block,
    # derived from the already-present signed net-of-tax delta.
    net_delta = facts.get("cross_country_comparison", {}).get("net_delta")
    facts["business_impact"] = dollarize_margin_leak(
        net_delta, annual_units=DEFAULT_ANNUAL_VOLUME_ASSUMPTION
    )

    seal_packet(PACKET, pairs, facts, load_signing_key())

    bi = facts["business_impact"]
    print(f"Re-sealed {PACKET} ({len(pairs)} captures unchanged).")
    if bi is None:
        print("  business_impact: None (no nonzero net-of-tax delta to dollarize).")
    else:
        print(
            f"  business_impact: {bi['net_of_tax_delta_per_unit']} EUR/unit "
            f"x {bi['annual_diverted_units']} units/yr (ASSUMPTION) = "
            f"{bi['recoverable_margin_eur_per_year']} EUR/yr recoverable margin "
            f"(dearer: {bi['dearer_country']})."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
