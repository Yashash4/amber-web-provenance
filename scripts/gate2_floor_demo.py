"""GATE-2 deterministic-half demonstration (NO Bright Data, NO fabricated 'live').

This proves the Component-2 PIPELINE wires together end-to-end:

    constructed capture records  ->  the deterministic floor (facts.json)
                                 ->  Component-1 seal_packet (signed packet)
                                 ->  verify_packet  ->  GREEN

It uses the committed demo signer key + the committed trusted allowlist, exactly
like the live path will. The capture BODIES here are **explicitly-labelled
constructed fixtures** (see facts.json `provenance`), NOT a Bright Data capture
and NOT presented as one — they exercise the floor logic so GATE-2's deterministic
half is verifiable WITHOUT credentials. The real same-second DE/BE residential
capture is the one step that runs when BD creds are provided (amber-capture).

Run::

    python scripts/gate2_floor_demo.py
    verify_packet samples/floor_demo_packet     # -> GREEN

Re-running overwrites the demo packet.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from amber.capture.harness import seal_from_records  # noqa: E402
from amber.capture.record import CaptureRecord  # noqa: E402
from amber.packet import verify_packet  # noqa: E402

URL = "https://shop.amber-demo.example/product/amber-hero-001"
GTIN = "4006381333931"  # check-digit-valid EAN-13
# Real RIPE-snapshot DE/BE exit IPs so the geo-attribution Source-1 is genuine.
DE_IPS = ["91.10.0.1", "91.10.0.2", "91.10.0.3"]
BE_IPS = ["91.176.0.1", "91.176.0.2", "91.176.0.3"]
OUT = REPO / "samples" / "floor_demo_packet"
KEY_PATH = REPO / "amber" / "keys" / "demo-signer.key"


def _body(price: str) -> bytes:
    # SAME gross price in both countries — the net-of-tax insight is that
    # identical shelf prices net out differently under DE 19% vs BE 21% VAT.
    return (
        b'{"sku":"AMBER-HERO-001","gtin":"' + GTIN.encode() + b'",'
        b'"price":"' + price.encode() + b'","currency":"EUR","availability":"InStock",'
        b'"_note":"CONSTRUCTED FIXTURE for the GATE-2 deterministic-floor demo; '
        b'NOT a Bright Data capture. The real capture runs via amber-capture with '
        b'BD credentials."}'
    )


def _records() -> list[CaptureRecord]:
    recs: list[CaptureRecord] = []
    for i, ip in enumerate(DE_IPS):
        recs.append(
            CaptureRecord(
                capture_id=f"de-{i + 1:02d}",
                url=URL,
                requested_country="DE",
                session_id=f"demo-de-{i + 1}",
                exit_ip=ip,
                requested_at="2026-05-29T00:00:01Z",
                http_status=200,
                headers={"content-type": "application/json", "content-language": "de-DE"},
                body=_body("129.99"),
            )
        )
    for i, ip in enumerate(BE_IPS):
        recs.append(
            CaptureRecord(
                capture_id=f"be-{i + 1:02d}",
                url=URL,
                requested_country="BE",
                session_id=f"demo-be-{i + 1}",
                exit_ip=ip,
                requested_at="2026-05-29T00:00:01Z",
                http_status=200,
                headers={"content-type": "application/json", "content-language": "nl-BE"},
                body=_body("129.99"),
            )
        )
    return recs


def _load_key() -> str:
    env = os.environ.get("AMBER_SIGNING_KEY", "").strip()
    if env:
        return env
    if KEY_PATH.exists():
        return KEY_PATH.read_text(encoding="ascii").strip()
    raise SystemExit(
        "No signing key. Set AMBER_SIGNING_KEY or place the demo key at "
        f"{KEY_PATH}. (Generate: python -c \"from amber.signer import "
        'generate_keypair; sk,pk=generate_keypair(); print(sk); print(pk)")'
    )


def main() -> int:
    key = _load_key()
    result = seal_from_records(
        OUT, URL, _records(), key, sku_label="AMBER-HERO-001 (DEMO FIXTURE)"
    )
    # Stamp provenance so no one mistakes this for a real capture.
    facts_path = OUT / "facts.json"  # already sealed; re-read for display only
    facts = json.loads(facts_path.read_bytes().decode("utf-8"))
    comp = facts["cross_country_comparison"]
    wcc = facts["within_country_control"]

    print(f"sealed -> {OUT}")
    print(f"  verify_packet (in-process): {'GREEN' if result.verify_ok else 'RED'}")
    print(f"  sku_identity              : {facts['sku_identity']['confidence']}")
    print(f"  primary_finding           : {comp['primary_finding']}")
    nd = comp["net_delta"]
    print(
        f"  net-of-tax delta          : {nd['net_of_tax_delta']} EUR "
        f"(DE net {nd['more_expensive_net']} vs BE net {nd['cheaper_net']}; "
        f"gross delta {nd['gross_delta']})"
    )
    print(f"  within-country agreement  : all_agree={wcc['all_intra_country_agree']}")
    for c in wcc["per_country"]:
        print(
            f"    {c['country']}: {c['n_purchasable_exits']} exits, "
            f"net {c['net_prices']} -> intra-spread {c['intra_country_spread']} "
            f"({c['agreement']})"
        )
    # Final independent CLI-equivalent verification against the committed allowlist.
    v = verify_packet(OUT)  # default = committed trusted_signers.txt
    verdict = "GREEN" if v.ok else "RED " + str(v.broken_node)
    print(f"\n  verify_packet (committed allowlist): {verdict}")
    print("\nNow run:  verify_packet samples/floor_demo_packet")
    return 0 if v.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
