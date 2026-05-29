"""The deterministic dollarization bridge: €/unit -> €/yr margin leak.

The bridge is a Layer-1, SIGNED fact, so it must be deterministic (no LLM, no
float drift) and must label the annual-volume input as a BUYER ASSUMPTION, never
as an observed measurement. These tests pin the arithmetic, the labeling, the
honest None cases, and that the figure is sealed into the real live packet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amber.business import DEFAULT_ANNUAL_VOLUME_ASSUMPTION, dollarize_margin_leak
from amber.capture import floor
from amber.capture.record import CaptureRecord

REPO = Path(__file__).resolve().parent.parent

URL = "https://shop.example/product/amber-hero-001"
GTIN = "4006381333931"


def _body(price: str) -> bytes:
    return (
        b'{"sku":"AMBER-HERO-001","gtin":"' + GTIN.encode() + b'",'
        b'"price":"' + price.encode() + b'","currency":"EUR",'
        b'"availability":"InStock",'
        b'"description":"a normal product response body, long enough to not look '
        b'degenerate to the soft-block detector"}'
    )


def _rec(cid: str, country: str, ip: str, price: str) -> CaptureRecord:
    return CaptureRecord(
        capture_id=cid,
        url=URL,
        requested_country=country,
        session_id=f"s-{cid}",
        exit_ip=ip,
        requested_at="2026-05-29T00:00:01Z",
        http_status=200,
        headers={"content-type": "application/json"},
        body=_body(price),
    )


def _de_be_records(de_gross: str, be_gross: str) -> list[CaptureRecord]:
    de_ips = ["91.10.0.1", "91.10.0.2", "91.10.0.3"]
    be_ips = ["91.176.0.1", "91.176.0.2", "91.176.0.3"]
    recs = [_rec(f"de-{i+1:02d}", "DE", ip, de_gross) for i, ip in enumerate(de_ips)]
    recs += [_rec(f"be-{i+1:02d}", "BE", ip, be_gross) for i, ip in enumerate(be_ips)]
    return recs


# --------------------------------------------------------------------------- #
# Pure-function determinism + labeling.
# --------------------------------------------------------------------------- #


def _net_delta(delta: str, *, dearer: str = "DE", cheaper: str = "BE") -> dict:
    return {
        "cheaper_country": cheaper,
        "more_expensive_country": dearer,
        "net_of_tax_delta": delta,
        "delta_is_nonzero": delta not in ("0", "0.00"),
    }


def test_multiplication_is_exact():
    bi = dollarize_margin_leak(_net_delta("10.75"), annual_units=50_000)
    assert bi is not None
    # 10.75 * 50000 = 537500.00 EXACTLY (Decimal, no float drift).
    assert bi["recoverable_margin_eur_per_year"] == "537500.00"
    assert bi["net_of_tax_delta_per_unit"] == "10.75"
    assert bi["annual_diverted_units"] == 50_000
    assert bi["dearer_country"] == "DE"
    assert bi["cheaper_country"] == "BE"
    assert bi["currency"] == "EUR"


def test_default_volume_is_the_labeled_assumption():
    bi = dollarize_margin_leak(_net_delta("10.75"))
    assert bi is not None
    assert bi["annual_diverted_units"] == DEFAULT_ANNUAL_VOLUME_ASSUMPTION == 50_000


def test_volume_is_explicitly_an_assumption_never_observed():
    bi = dollarize_margin_leak(_net_delta("10.75"))
    assert bi is not None
    assert bi["annual_diverted_units_is_assumption"] is True
    assert bi["volume_basis"] == "buyer-supplied volume assumption"
    assert "ASSUMPTION" in bi["disclaimer"]
    assert "not an Amber measurement" in bi["disclaimer"]
    # The computation is transparent (reproducible from the signed inputs).
    assert bi["computation"] == "net_of_tax_delta_per_unit * annual_diverted_units"


def test_deterministic_repeatable():
    first = dollarize_margin_leak(_net_delta("3.33"), annual_units=12_345)
    second = dollarize_margin_leak(_net_delta("3.33"), annual_units=12_345)
    assert first == second
    assert first is not None
    # 3.33 * 12345 = 41108.85
    assert first["recoverable_margin_eur_per_year"] == "41108.85"


def test_zero_delta_does_not_dollarize():
    assert dollarize_margin_leak(_net_delta("0.00")) is None


def test_no_net_delta_block_is_none():
    """A denial-only / inconclusive comparison has no net_delta to dollarize."""
    assert dollarize_margin_leak(None) is None


def test_custom_volume():
    bi = dollarize_margin_leak(_net_delta("10.75"), annual_units=100_000)
    assert bi is not None
    assert bi["recoverable_margin_eur_per_year"] == "1075000.00"


def test_nonpositive_volume_rejected():
    with pytest.raises(ValueError):
        dollarize_margin_leak(_net_delta("10.75"), annual_units=0)
    with pytest.raises(ValueError):
        dollarize_margin_leak(_net_delta("10.75"), annual_units=-5)


# --------------------------------------------------------------------------- #
# Wiring through the floor (the SIGNED Layer-1 fact).
# --------------------------------------------------------------------------- #


def test_build_facts_includes_business_impact():
    facts = floor.build_facts(URL, _de_be_records("129.99", "129.99"))
    bi = facts["business_impact"]
    assert bi is not None
    # net_DE 109.24 vs net_BE 107.43 -> delta 1.81; * 50000 = 90500.00
    assert bi["net_of_tax_delta_per_unit"] == "1.81"
    assert bi["recoverable_margin_eur_per_year"] == "90500.00"
    assert bi["annual_diverted_units_is_assumption"] is True


def test_build_facts_business_impact_none_when_no_delta():
    # Identical NET price (pick grosses that net equal) -> no nonzero delta.
    # DE 119.00/1.19 = 100.00 ; BE 121.00/1.21 = 100.00 -> delta 0 -> None.
    facts = floor.build_facts(URL, _de_be_records("119.00", "121.00"))
    assert facts["cross_country_comparison"]["net_delta"]["delta_is_nonzero"] is False
    assert facts["business_impact"] is None


def test_build_facts_volume_knob_threads_through():
    facts = floor.build_facts(
        URL, _de_be_records("129.99", "129.99"), annual_volume_assumption=200_000
    )
    bi = facts["business_impact"]
    assert bi is not None
    assert bi["annual_diverted_units"] == 200_000
    # 1.81 * 200000 = 362000.00
    assert bi["recoverable_margin_eur_per_year"] == "362000.00"


# --------------------------------------------------------------------------- #
# The REAL live packet carries the dollarization fact inside the signed bundle.
# --------------------------------------------------------------------------- #


def test_live_packet_has_signed_dollarization():
    facts = json.loads((REPO / "samples" / "live_packet" / "facts.json").read_text("utf-8"))
    bi = facts.get("business_impact")
    assert bi is not None, "live packet was not re-sealed with business_impact"
    assert bi["net_of_tax_delta_per_unit"] == "10.75"
    assert bi["recoverable_margin_eur_per_year"] == "537500.00"
    assert bi["dearer_country"] == "DE"
    assert bi["annual_diverted_units_is_assumption"] is True
