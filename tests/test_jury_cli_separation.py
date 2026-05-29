"""Tests that the CLI advisory is PHYSICALLY SEPARATE from the signed packet.

LOCK 4: the AI legal label is a separate, UNSIGNED advisory — never written into
the signed Layer-1 packet. These tests seal a real packet (reusing the Phase-1
core, unmodified), run the jury CLI against it with a mocked client, and assert:
  * the advisory lands OUTSIDE the packet dir (a sibling file);
  * no advisory file appears inside the packet;
  * the packet still verifies GREEN after the jury ran (untouched);
  * the on-disk advisory JSON is flagged unsigned with the disclaimer.
"""

from __future__ import annotations

import json

import amber.jury.cli as jcli
from amber.jury import taxonomy
from amber.jury.client import JuryModels
from amber.packet import verify_packet
from tests.test_jury_consensus import FakeClient, _reply

MODELS = JuryModels(openai="m-openai", google="m-google", anthropic="m-anthropic")


def _seal_real_packet(tmp_path):
    """Seal a 2-capture packet using the unmodified Phase-1 core."""
    from amber.packet import CaptureInput, seal_packet
    from amber.signer import generate_keypair

    priv, pub = generate_keypair()
    captures = [
        (
            CaptureInput(
                capture_id="de-01",
                url="https://shop.example/p/amber-hero-001",
                country="DE",
                exit_ip="91.10.20.30",
                requested_at="2026-05-29T00:00:01Z",
                http_status=200,
                headers={"content-language": "de-DE"},
            ),
            b'{"price_gross":"129.99","currency":"EUR","country":"DE"}',
        ),
        (
            CaptureInput(
                capture_id="be-01",
                url="https://shop.example/p/amber-hero-001",
                country="BE",
                exit_ip="81.40.50.60",
                requested_at="2026-05-29T00:00:01Z",
                http_status=403,
                headers={"content-language": "nl-BE"},
            ),
            b'{"error":"not available in your region"}',
        ),
    ]
    facts = {
        "schema": "amber/facts@2",
        "url": "https://shop.example/p/amber-hero-001",
        "countries": ["BE", "DE"],
        "cross_country_comparison": {
            "primary_finding": "ACCESS_OR_PAYMENT_DENIAL",
            "net_delta": None,
            "access_denial": {"geo_blocked_countries": ["BE"], "purchasable_countries": ["DE"]},
            "per_country_states": {"BE": ["GEO_BLOCKED"], "DE": ["PURCHASABLE"]},
        },
        "within_country_control": {"all_intra_country_agree": True, "per_country": []},
    }
    pkt = tmp_path / "amber_packet"
    seal_packet(pkt, captures, facts, priv)
    return pkt, pub


def _files_inside(pkt):
    return {p.name for p in pkt.iterdir()}


def test_advisory_written_outside_packet_and_packet_unchanged(tmp_path, monkeypatch):
    pkt, pub = _seal_real_packet(tmp_path)
    before = _files_inside(pkt)

    # Packet verifies GREEN before the jury runs.
    assert verify_packet(pkt, expected_pubkeys={pub}).ok is True

    # Mock the network: a clean PROHIBITED_GEO_BLOCKING majority.
    fake = FakeClient({m: _reply(taxonomy.PROHIBITED_GEO_BLOCKING) for m in MODELS.as_tuple()})
    monkeypatch.setattr(jcli, "run_jury", lambda facts: __run(fake, facts))

    rc = jcli.main(["classify", str(pkt)])
    assert rc == 0

    # 1. The packet directory is byte-for-byte the same set of files (no
    #    advisory leaked inside).
    after = _files_inside(pkt)
    assert after == before
    assert "legal_advisory.json" not in after

    # 2. The advisory is a SIBLING of the packet dir.
    sibling = pkt.parent / f"{pkt.name}.legal_advisory.json"
    assert sibling.exists()

    # 3. The packet STILL verifies GREEN (the jury did not touch the signed bundle).
    assert verify_packet(pkt, expected_pubkeys={pub}).ok is True

    # 4. The on-disk advisory is flagged unsigned + carries the disclaimer.
    adv = json.loads(sibling.read_text(encoding="utf-8"))
    assert adv["signed"] is False
    assert adv["layer"] == "LAYER_2_INTERPRETATION"
    assert "NOT legal advice" in adv["disclaimer"]
    assert adv["advisory_label"] == taxonomy.PROHIBITED_GEO_BLOCKING


def __run(fake_client, facts):
    """Helper: call the real run_jury with the injected fake client + test models."""
    from amber.jury.jury import run_jury

    return run_jury(facts, client=fake_client, models=MODELS)


def test_classify_missing_facts_returns_error(tmp_path):
    empty = tmp_path / "empty_packet"
    empty.mkdir()
    rc = jcli.main(["classify", str(empty)])
    assert rc == 2  # no facts.json


def test_classify_non_directory_returns_error(tmp_path):
    rc = jcli.main(["classify", str(tmp_path / "nope")])
    assert rc == 2
