"""Tests for the deterministic persistence analysis.

These cover the operational verdicts (baseline / persistent / intermittent /
transient / no-gap), the HONEST real-window framing (never an invented multi-week
chart; a single capture is a one-point baseline), and recurrence. No network, no
cognee, no LLM.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amber.memory.observations import Observation, observation_from_packet
from amber.memory.persistence import (
    BASELINE,
    INTERMITTENT,
    NO_GAP,
    PERSISTENT,
    TRANSIENT,
    analyze_recurrence,
    analyze_sku,
    group_by_sku,
)

LIVE_PACKET = Path(__file__).resolve().parent.parent / "samples" / "live_packet"


def _obs(
    packet_id: str,
    *,
    gtin: str = "00195949689673",
    delta: str | None = "10.75",
    nonzero: bool | None = True,
    when: str | None = "2026-05-29T16:29:40Z",
    agree: bool | None = True,
) -> Observation:
    return Observation(
        packet_id=packet_id,
        schema="amber/facts@2",
        sku_label="Apple AirPods 4",
        canonical_gtin=gtin,
        sku_identity_confidence="GTIN_MATCH",
        countries=("BE", "DE"),
        primary_finding="NET_OF_TAX_PRICE_DELTA",
        net_of_tax_delta=delta,
        gross_delta="10.00",
        more_expensive_country="DE",
        cheaper_country="BE",
        more_expensive_net="150.42",
        cheaper_net="139.67",
        delta_is_nonzero=nonzero,
        within_country_all_agree=agree,
        dispatched_same_second=True,
        dispatched_at_values=(when,) if when else (),
        witnessed_at_values=(),
        observed_at=when,
        captures=(),
    )


def test_single_capture_is_a_baseline_not_a_trend():
    """One signed capture with a gap is a BASELINE — persistence is NOT asserted."""
    rep = analyze_sku([_obs("p1")])
    assert rep.verdict == BASELINE
    assert rep.n_captures == 1
    assert "one-point baseline" in rep.real_window
    assert "baseline compounds from day one" in rep.real_window
    # The honest framing must NEVER claim a multi-week history.
    assert "26 week" not in rep.real_window.lower()
    assert "persistence cannot be asserted" in rep.rationale


def test_single_capture_no_gap_is_no_gap():
    rep = analyze_sku([_obs("p1", delta="0.00", nonzero=False)])
    assert rep.verdict == NO_GAP


def test_gap_in_every_capture_is_persistent():
    obs = [
        _obs("p1", when="2026-05-29T16:29:40Z"),
        _obs("p2", when="2026-05-30T16:29:40Z"),
        _obs("p3", when="2026-05-31T16:29:40Z"),
    ]
    rep = analyze_sku(obs)
    assert rep.verdict == PERSISTENT
    assert rep.n_captures == 3
    assert rep.captures_with_gap == 3
    # Real window spans first..last; honest forward-looking framing.
    assert "3 captures over" in rep.real_window
    assert rep.first_seen == "2026-05-29T16:29:40Z"
    assert rep.last_seen == "2026-05-31T16:29:40Z"
    assert "sustained" in rep.rationale


def test_gap_in_some_captures_including_latest_is_intermittent():
    obs = [
        _obs("p1", when="2026-05-29T00:00:00Z", delta="10.75", nonzero=True),
        _obs("p2", when="2026-05-30T00:00:00Z", delta="0.00", nonzero=False),
        _obs("p3", when="2026-05-31T00:00:00Z", delta="10.75", nonzero=True),
    ]
    rep = analyze_sku(obs)
    assert rep.verdict == INTERMITTENT
    assert rep.captures_with_gap == 2


def test_gap_that_disappears_in_latest_is_transient():
    obs = [
        _obs("p1", when="2026-05-29T00:00:00Z", delta="10.75", nonzero=True),
        _obs("p2", when="2026-05-30T00:00:00Z", delta="10.75", nonzero=True),
        _obs("p3", when="2026-05-31T00:00:00Z", delta="0.00", nonzero=False),
    ]
    rep = analyze_sku(obs)
    assert rep.verdict == TRANSIENT
    assert rep.captures_with_gap == 2


def test_chronological_order_independent_of_input_order():
    """Verdict uses the REAL timestamps to order, not list order."""
    # Latest capture (p3) has NO gap -> TRANSIENT, even if passed out of order.
    obs = [
        _obs("p3", when="2026-05-31T00:00:00Z", delta="0.00", nonzero=False),
        _obs("p1", when="2026-05-29T00:00:00Z", delta="10.75", nonzero=True),
        _obs("p2", when="2026-05-30T00:00:00Z", delta="10.75", nonzero=True),
    ]
    rep = analyze_sku(obs)
    assert rep.verdict == TRANSIENT
    assert rep.first_seen == "2026-05-29T00:00:00Z"
    assert rep.last_seen == "2026-05-31T00:00:00Z"


def test_within_country_corroboration_requires_every_capture():
    obs = [_obs("p1", agree=True), _obs("p2", when="2026-05-30T00:00:00Z", agree=False)]
    rep = analyze_sku(obs)
    assert rep.within_country_corroborated is False


def test_analyze_sku_empty_raises():
    with pytest.raises(ValueError):
        analyze_sku([])


def test_recurrence_groups_by_gtin():
    obs = [
        _obs("p1", gtin="00195949689673", when="2026-05-29T00:00:00Z"),
        _obs("p2", gtin="00195949689673", when="2026-05-30T00:00:00Z"),
        _obs("p3", gtin="04006381333931", when="2026-05-29T00:00:00Z"),
    ]
    rec = analyze_recurrence(obs)
    assert rec.n_observations == 3
    assert rec.n_distinct_skus == 2
    assert len(rec.recurring_skus) == 1  # only the AirPods GTIN recurs
    assert rec.recurring_skus[0]["canonical_gtin"] == "00195949689673"
    assert rec.recurring_skus[0]["n_captures"] == 2
    # Country pair BE/DE seen in all three.
    assert rec.country_pair_counts[0] == ("BE/DE", 3)


def test_real_airpods_packet_persistence_is_a_baseline():
    """ONE real signed packet -> a one-point BASELINE (the honest answer)."""
    obs = observation_from_packet(LIVE_PACKET)
    rep = analyze_sku([obs])
    assert rep.verdict == BASELINE
    assert rep.canonical_gtin == "00195949689673"
    assert rep.latest_net_of_tax_delta == "10.75"
    assert rep.within_country_corroborated is True
    assert "one-point baseline" in rep.real_window


def test_group_by_sku_prefers_gtin():
    obs = [_obs("p1"), _obs("p2", when="2026-05-30T00:00:00Z")]
    buckets = group_by_sku(obs)
    assert list(buckets.keys()) == ["00195949689673"]
    assert len(buckets["00195949689673"]) == 2
