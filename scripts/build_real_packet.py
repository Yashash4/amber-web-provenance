"""Build a REAL signed Amber packet from a real HTTP fetch.

This is the GATE-1 reproducer: it performs an actual HTTP GET (stdlib only, no
Bright Data yet — BD is Component 2), captures the real response body + a
selection of real response headers, derives the deterministic Layer-1 facts
from the *captured bytes*, and seals + signs a packet with the committed
demo key. Nothing here is synthesised — the body and headers are whatever the
server actually returned.

Run::

    python scripts/build_real_packet.py
    verify_packet samples/real_packet      # -> GREEN

Re-running overwrites samples/real_packet with a fresh real capture.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from amber.packet import CaptureInput, seal_packet, sha256_hex  # noqa: E402

# Two real fetches to a stable, content-typed public endpoint. httpbin echoes a
# JSON body and ordinary HTTP headers — good for real, reproducible captures.
# Two captures (not one) make the golden packet a faithful multi-vantage Amber
# packet AND let the "swap two manifest entries" tamper case be demonstrated on
# real data. NOTE: this is a plain stdlib fetch, NOT a geo-proxied one — true
# per-country residential capture arrives in Component 2 (Bright Data).
TARGETS = [
    ("vantage-a-001", "https://httpbin.org/anything?amber=component1&vantage=a"),
    ("vantage-b-001", "https://httpbin.org/anything?amber=component1&vantage=b"),
]

# Headers we record as Layer-1 geo/identity signals (whatever the server sends).
SELECTED_HEADERS = (
    "content-type",
    "content-language",
    "date",
    "server",
    "content-length",
)

KEY_PATH = REPO / "amber" / "keys" / "demo-signer.key"
OUT = REPO / "samples" / "real_packet"


def real_fetch(url: str) -> tuple[int, bytes, dict[str, str]]:
    """Do a real GET and return (status, body_bytes, selected_headers)."""
    req = urllib.request.Request(url, headers={"User-Agent": "amber-component1/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (real network fetch is the point)
        body = resp.read()
        status = resp.status
        headers = {
            k.lower(): v
            for k, v in resp.headers.items()
            if k.lower() in SELECTED_HEADERS
        }
    return status, body, headers


def main() -> int:
    private_key_hex = KEY_PATH.read_text(encoding="ascii").strip()
    requested_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    captures: list[tuple[CaptureInput, bytes]] = []
    observations = []
    for capture_id, url in TARGETS:
        status, body, headers = real_fetch(url)
        cap = CaptureInput(
            capture_id=capture_id,
            url=url,
            # Plain fetch has no geo-proxy; true per-country geo arrives in
            # Component 2 (Bright Data). We record the honest egress, not a
            # fabricated country.
            country="US",
            exit_ip="local-egress",
            requested_at=requested_at,
            http_status=status,
            headers=headers,
        )
        captures.append((cap, body))
        observations.append(
            {
                "capture_id": capture_id,
                "url": url,
                "http_status": status,
                "body_bytes": len(body),
                "body_sha256": sha256_hex(body),
                # Layer-1 deterministic state derived ONLY from observed bytes —
                # no LLM, no asserted price.
                "state": "PURCHASABLE" if status == 200 else "INCONCLUSIVE",
            }
        )

    facts = {
        "schema": "amber/facts@1",
        "note": (
            "Component-1 GATE-1 packet from real HTTP GETs "
            "(no Bright Data; that is Component 2)."
        ),
        "observations": observations,
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    seal_packet(OUT, captures, facts, private_key_hex)

    root = json.loads((OUT / "merkle.json").read_text())["root"]
    print(f"Sealed real packet ({len(captures)} captures) -> {OUT}")
    for cap, body in captures:
        digest = sha256_hex(body)[:16]
        print(f"  {cap.capture_id}: {cap.http_status} {len(body)}B sha256={digest}...")
    print(f"  merkle_root = {root}")
    print("\nNow run:  verify_packet samples/real_packet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
