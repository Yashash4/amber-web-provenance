"""Tests for the deterministic Layer-1 -> memory-observation mapping.

These assert that the REAL signed AirPods packet's facts map correctly into an
Observation, and that nothing is fabricated (missing fields stay None; real
timestamps are used, never invented). No network, no cognee.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amber.memory.observations import (
    FactsParseError,
    Observation,
    observation_from_facts,
    observation_from_packet,
)

# The real DE/BE AirPods capture committed by Component 2.
LIVE_PACKET = Path(__file__).resolve().parent.parent / "samples" / "live_packet"
FLOOR_PACKET = Path(__file__).resolve().parent.parent / "samples" / "floor_demo_packet"


def test_real_airpods_packet_maps_correctly():
    """The committed REAL AirPods facts.json maps to the documented numbers."""
    obs = observation_from_packet(LIVE_PACKET)

    assert isinstance(obs, Observation)
    assert obs.packet_id == "live_packet"
    assert obs.canonical_gtin == "00195949689673"
    assert obs.sku_identity_confidence == "GTIN_MATCH"
    assert obs.countries == ("BE", "DE")
    assert obs.primary_finding == "NET_OF_TAX_PRICE_DELTA"
    # The real net-of-tax delta is 10.75 EUR; DE is the more expensive net.
    assert obs.net_of_tax_delta == "10.75"
    assert obs.gross_delta == "10.00"
    assert obs.more_expensive_country == "DE"
    assert obs.cheaper_country == "BE"
    assert obs.more_expensive_net == "150.42"
    assert obs.cheaper_net == "139.67"
    assert obs.delta_is_nonzero is True
    # Within-country control agreed in both countries (real packet).
    assert obs.within_country_all_agree is True
    # The same-second dispatch evidence is real and present in this packet.
    assert obs.dispatched_same_second is True
    assert obs.dispatched_at_values == ("2026-05-29T16:29:40Z",)
    # observed_at is the earliest REAL timestamp — never synthesized.
    assert obs.observed_at == "2026-05-29T16:29:40Z"


def test_real_packet_per_capture_exits_mapped():
    """Each residential exit is carried with its REAL IP + RIR registry."""
    obs = observation_from_packet(LIVE_PACKET)
    assert len(obs.captures) == 6
    de = [c for c in obs.captures if c.country == "DE"]
    be = [c for c in obs.captures if c.country == "BE"]
    assert len(de) == 3 and len(be) == 3
    # Three distinct DE exit IPs (the within-country control witnesses).
    assert len({c.exit_ip for c in de}) == 3
    for c in obs.captures:
        assert c.rir_registry == "ripencc"
        assert c.state == "PURCHASABLE"
        assert c.currency == "EUR"
    # DE net 150.42, BE net 139.67 — the deterministic, VAT-corrected figures.
    assert all(c.net_price == "150.42" for c in de)
    assert all(c.net_price == "139.67" for c in be)


def test_floor_demo_fixture_maps_correctly():
    """The constructed (labelled) floor fixture also maps; delta 1.81 EUR."""
    obs = observation_from_packet(FLOOR_PACKET)
    assert obs.net_of_tax_delta == "1.81"
    assert obs.more_expensive_country == "DE"
    # The fixture's batch is stamped same-second (true) but has no dispatch stamp.
    assert obs.dispatched_same_second is None
    assert obs.witnessed_at_values == ("2026-05-29T00:00:01Z",)
    assert obs.observed_at == "2026-05-29T00:00:01Z"


def test_missing_fields_are_never_fabricated():
    """A minimal facts@2 object: absent optional fields stay None, not invented."""
    facts = {
        "schema": "amber/facts@2",
        "countries": ["DE", "BE"],
        # no sku_identity, no cross_country_comparison, no timestamps, no captures
    }
    obs = observation_from_facts(facts, packet_id="minimal")
    assert obs.canonical_gtin is None
    assert obs.net_of_tax_delta is None
    assert obs.more_expensive_country is None
    assert obs.within_country_all_agree is None
    assert obs.dispatched_same_second is None
    assert obs.observed_at is None  # no timestamp invented
    assert obs.captures == ()


def test_unsupported_schema_raises():
    with pytest.raises(FactsParseError):
        observation_from_facts({"schema": "amber/facts@1"}, packet_id="old")


def test_missing_facts_file_raises(tmp_path):
    empty = tmp_path / "empty_packet"
    empty.mkdir()
    with pytest.raises(FactsParseError):
        observation_from_packet(empty)


def test_observation_as_dict_is_json_serializable():
    obs = observation_from_packet(LIVE_PACKET)
    # Must round-trip through JSON (it is persisted as the memory artifact).
    d = obs.as_dict()
    json.dumps(d)
    assert d["canonical_gtin"] == "00195949689673"
    assert isinstance(d["captures"], list)
    assert len(d["captures"]) == 6
