"""Shared fixtures: a real-bytes, multi-capture sealed packet.

The fixture seals a packet from REAL captured-style bodies (raw bytes, not
mocked return values) using a freshly generated keypair, into a pytest tmp
dir. Multiple captures are used so the "swap two manifest entries" tamper case
is meaningful.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amber.packet import CaptureInput, seal_packet
from amber.signer import generate_keypair

# Two real-shaped capture bodies. These are exact bytes that get hashed +
# Merkle-committed; the German one is more expensive net-of-tax than Belgium.
DE_BODY = (
    b'{"sku":"AMBER-HERO-001","gtin":"04006381333931",'
    b'"price_gross":"129.99","currency":"EUR","country":"DE","vat_rate":"0.19"}'
)
BE_BODY = (
    b'{"sku":"AMBER-HERO-001","gtin":"04006381333931",'
    b'"price_gross":"109.99","currency":"EUR","country":"BE","vat_rate":"0.21"}'
)


@pytest.fixture
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def sealed_packet(tmp_path: Path, keypair: tuple[str, str]) -> dict:
    """Seal a 2-capture packet and return paths + the private key."""
    private_key_hex, public_key_hex = keypair

    captures = [
        (
            CaptureInput(
                capture_id="de-01",
                url="https://shop.example/product/amber-hero-001",
                country="DE",
                exit_ip="91.10.20.30",
                requested_at="2026-05-29T00:00:01Z",
                http_status=200,
                headers={"content-language": "de-DE", "content-type": "application/json"},
            ),
            DE_BODY,
        ),
        (
            CaptureInput(
                capture_id="be-01",
                url="https://shop.example/product/amber-hero-001",
                country="BE",
                exit_ip="81.40.50.60",
                requested_at="2026-05-29T00:00:01Z",
                http_status=200,
                headers={"content-language": "nl-BE", "content-type": "application/json"},
            ),
            BE_BODY,
        ),
    ]

    # Layer-1 deterministic facts (no LLM). Net-of-tax spread computed from the
    # captured gross prices + the sourced VAT rates.
    facts = {
        "schema": "amber/facts@1",
        "sku": "AMBER-HERO-001",
        "gtin": "04006381333931",
        "sku_identity_confidence": "GTIN_MATCH",
        "per_geo": [
            {
                "country": "DE", "price_gross": "129.99", "vat_rate": "0.19",
                "price_net": "109.24", "state": "PURCHASABLE",
            },
            {
                "country": "BE", "price_gross": "109.99", "vat_rate": "0.21",
                "price_net": "90.90", "state": "PURCHASABLE",
            },
        ],
        "net_of_tax_spread_eur": "18.34",
    }

    out = tmp_path / "amber_packet"
    seal_packet(out, captures, facts, private_key_hex)

    return {
        "dir": out,
        "private_key_hex": private_key_hex,
        "public_key_hex": public_key_hex,
        "facts": facts,
    }


def read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def write_json_canonical(path: Path, obj: dict) -> None:
    """Write JSON in the same canonical form seal_packet uses."""
    from amber.signer import canonical_json

    path.write_bytes(canonical_json(obj))
