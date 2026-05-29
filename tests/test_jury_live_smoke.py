"""ONE guarded live smoke test against the real AI/ML API.

Skipped by default so the suite never burns credits. Enable with::

    AMBER_JURY_LIVE=1 pytest tests/test_jury_live_smoke.py -q

It hits the real gateway on a SINGLE example to confirm end-to-end wiring (key
resolution -> three model calls -> parse -> consensus). It asserts only that the
jury ran and produced a valid advisory shape — never a specific label (the
models legitimately disagree on borderline cases, which is the whole point of
routing to a human).
"""

from __future__ import annotations

import os

import pytest

from amber.jury import taxonomy
from amber.jury.client import APIKeyMissing, load_api_key

LIVE = os.environ.get("AMBER_JURY_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="live AI/ML API smoke test; set AMBER_JURY_LIVE=1 to run",
)


_FACTS = {
    "schema": "amber/facts@2",
    "url": "https://shop.amber-demo.example/product/amber-hero-001",
    "sku_label": "AMBER-HERO-001 (DEMO FIXTURE)",
    "countries": ["BE", "DE"],
    "cross_country_comparison": {
        "primary_finding": "ACCESS_OR_PAYMENT_DENIAL",
        "net_delta": None,
        "access_denial": {"geo_blocked_countries": ["BE"], "purchasable_countries": ["DE"]},
        "per_country_states": {"BE": ["GEO_BLOCKED"], "DE": ["PURCHASABLE"]},
    },
    "within_country_control": {"all_intra_country_agree": True, "per_country": []},
}


def test_live_jury_runs_and_returns_valid_advisory():
    try:
        load_api_key()
    except APIKeyMissing:
        pytest.skip("no AI/ML API key available for the live smoke test")

    from amber.jury.jury import run_jury

    advisory = run_jury(_FACTS)  # real client, real network

    assert len(advisory.jurors) == 3
    # At least one model must have actually answered (otherwise wiring is broken).
    assert any(j.ok for j in advisory.jurors)
    for j in advisory.jurors:
        assert taxonomy.is_valid_label(j.label)
    # The advisory label is a valid token or the routing outcome.
    assert (
        taxonomy.is_valid_label(advisory.advisory_label)
        or advisory.advisory_label == taxonomy.ROUTE_TO_HUMAN
    )
    assert advisory.signed is False
