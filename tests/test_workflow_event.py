"""Tests for deterministic event extraction from signed Layer-1 facts."""

from __future__ import annotations

import dataclasses
import json
from decimal import Decimal
from pathlib import Path

import pytest

from amber.workflow.event import (
    KIND_ACCESS_DENIAL,
    KIND_NET_DELTA,
    AmberEvent,
    EventThreshold,
    NoEventError,
    extract_event,
    load_facts,
)

REPO = Path(__file__).resolve().parent.parent
LIVE_PACKET = REPO / "samples" / "live_packet"


def _net_delta_facts(delta: str = "10.75") -> dict:
    """A minimal facts.json shaped like the floor's amber/facts@2 output."""
    return {
        "schema": "amber/facts@2",
        "sku_label": "Apple AirPods 4 (ANC) GTIN 0195949689673",
        "countries": ["BE", "DE"],
        "dispatched_same_second": True,
        "same_second_batch": False,
        "sku_identity": {"confidence": "GTIN_MATCH"},
        "within_country_control": {"all_intra_country_agree": True},
        "cross_country_comparison": {
            "primary_finding": "NET_OF_TAX_PRICE_DELTA",
            "net_delta": {
                "cheaper_country": "BE",
                "more_expensive_country": "DE",
                "cheaper_net": "139.67",
                "more_expensive_net": "150.42",
                "net_of_tax_delta": delta,
                "gross_delta": "10.00",
                "delta_is_nonzero": True,
            },
            "access_denial": None,
            "per_country_states": {"BE": ["PURCHASABLE"], "DE": ["PURCHASABLE"]},
        },
    }


def _denial_facts() -> dict:
    return {
        "schema": "amber/facts@2",
        "sku_label": "Some Gadget",
        "countries": ["BE", "DE"],
        "sku_identity": {"confidence": "GTIN_MATCH"},
        "cross_country_comparison": {
            "primary_finding": "ACCESS_OR_PAYMENT_DENIAL",
            "net_delta": None,
            "access_denial": {
                "geo_blocked_countries": ["BE"],
                "purchasable_countries": ["DE"],
            },
            "per_country_states": {"BE": ["GEO_BLOCKED"], "DE": ["PURCHASABLE"]},
        },
    }


def test_extract_net_delta_above_threshold():
    event = extract_event(_net_delta_facts("10.75"), EventThreshold.from_eur("1.00"))
    assert event.kind == KIND_NET_DELTA
    assert event.net_of_tax_delta_eur == Decimal("10.75")
    assert event.more_expensive_country == "DE"
    assert event.cheaper_country == "BE"
    assert event.within_country_control_agree is True
    assert event.sku_identity_confidence == "GTIN_MATCH"
    assert "violation" not in event.fact_banner.lower()
    assert "PRICE DELTA DETECTED" in event.fact_banner


def test_threshold_boundary_equal_does_not_fire():
    # delta == threshold -> NOT an event (strictly above).
    with pytest.raises(NoEventError):
        extract_event(_net_delta_facts("10.75"), EventThreshold.from_eur("10.75"))


def test_threshold_boundary_just_above_fires():
    event = extract_event(_net_delta_facts("10.76"), EventThreshold.from_eur("10.75"))
    assert event.net_of_tax_delta_eur == Decimal("10.76")


def test_sub_threshold_raises_no_event():
    with pytest.raises(NoEventError):
        extract_event(_net_delta_facts("0.50"), EventThreshold.from_eur("1.00"))


def test_high_threshold_suppresses_real_delta():
    with pytest.raises(NoEventError):
        extract_event(_net_delta_facts("10.75"), EventThreshold.from_eur("25.00"))


def test_access_denial_is_an_event_without_threshold():
    event = extract_event(_denial_facts())
    assert event.kind == KIND_ACCESS_DENIAL
    assert event.geo_blocked_countries == ("BE",)
    assert event.purchasable_countries == ("DE",)
    assert event.net_of_tax_delta_eur is None
    assert "violation" not in event.fact_banner.lower()


def test_no_net_delta_control_raises():
    facts = _net_delta_facts("0.00")
    facts["cross_country_comparison"]["primary_finding"] = "NO_NET_DELTA"
    with pytest.raises(NoEventError):
        extract_event(facts)


def test_inconclusive_raises():
    facts = _net_delta_facts("5.00")
    facts["cross_country_comparison"]["primary_finding"] = "INCONCLUSIVE"
    with pytest.raises(NoEventError):
        extract_event(facts)


def test_missing_comparison_block_raises():
    with pytest.raises(NoEventError):
        extract_event({"schema": "amber/facts@2"})


def test_as_row_serialises_money_as_strings():
    event = extract_event(_net_delta_facts("10.75"))
    row = event.as_row()
    assert row["net_of_tax_delta_eur"] == "10.75"
    assert row["threshold_eur"] == "1.00"
    assert row["fact_banner"]
    # No verdict language anywhere in the row.
    assert "violation" not in json.dumps(row).lower()


def test_event_dataclass_is_frozen():
    event = extract_event(_net_delta_facts())
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.kind = "x"  # type: ignore[misc]


@pytest.mark.skipif(not LIVE_PACKET.exists(), reason="live_packet sample missing")
def test_real_live_packet_event_is_the_10_75_delta():
    """The shipped real DE/BE AirPods packet yields the €10.75 net-of-tax delta."""
    facts = load_facts(LIVE_PACKET)
    event = extract_event(facts, EventThreshold.from_eur("1.00"))
    assert event.kind == KIND_NET_DELTA
    assert event.net_of_tax_delta_eur == Decimal("10.75")
    assert event.more_expensive_country == "DE"
    assert event.cheaper_country == "BE"
    assert event.within_country_control_agree is True
    assert event.sku_identity_confidence == "GTIN_MATCH"
    assert event.dispatched_same_second is True
    assert isinstance(event, AmberEvent)


@pytest.mark.skipif(not LIVE_PACKET.exists(), reason="live_packet sample missing")
def test_load_facts_does_not_mutate_packet():
    """Reading the packet for an event must not change any packet bytes."""
    before = {p.name: p.read_bytes() for p in LIVE_PACKET.iterdir() if p.is_file()}
    facts = load_facts(LIVE_PACKET)
    extract_event(facts)
    after = {p.name: p.read_bytes() for p in LIVE_PACKET.iterdir() if p.is_file()}
    assert before == after
