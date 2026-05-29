"""VAT table + net-of-tax computation tests (deterministic, Decimal-exact)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from amber.capture import vat


def test_hero_pair_rates_present_and_sourced():
    de = vat.lookup_rate("DE")
    be = vat.lookup_rate("BE")
    assert de is not None and be is not None
    assert de.rate == Decimal("0.19")
    assert be.rate == Decimal("0.21")
    # Every rate carries a non-empty source + an as_of date (auditability).
    for r in (de, be):
        assert r.source and "European Commission" in r.source
        assert r.as_of == "2025-01-01"


def test_lookup_unknown_country_returns_none_not_default():
    # Never default to standard — surface the gap.
    assert vat.lookup_rate("ZZ") is None
    assert vat.lookup_rate("DE", "nonexistent-category") is None


def test_reduced_rate_books_distinct_from_standard():
    assert vat.lookup_rate("DE", vat.CATEGORY_BOOKS).rate == Decimal("0.07")
    assert vat.lookup_rate("BE", vat.CATEGORY_BOOKS).rate == Decimal("0.06")


NET_CASES = [
    # (gross, rate, expected_net) — net = gross / (1 + rate), 2dp HALF_UP.
    (Decimal("129.99"), Decimal("0.19"), Decimal("109.24")),
    (Decimal("109.99"), Decimal("0.21"), Decimal("90.90")),
    (Decimal("100.00"), Decimal("0.20"), Decimal("83.33")),
    (Decimal("0.00"), Decimal("0.19"), Decimal("0.00")),
    (Decimal("1.00"), Decimal("0.00"), Decimal("1.00")),  # zero VAT -> net == gross
]


@pytest.mark.parametrize("gross,rate,expected", NET_CASES)
def test_net_of_tax(gross, rate, expected):
    assert vat.net_of_tax(gross, rate) == expected


def test_net_of_tax_rejects_negative():
    with pytest.raises(ValueError):
        vat.net_of_tax(Decimal("-1"), Decimal("0.19"))
    with pytest.raises(ValueError):
        vat.net_of_tax(Decimal("1"), Decimal("-0.19"))


def test_same_gross_different_vat_yields_a_net_difference():
    """The whole point: identical GROSS prices net out DIFFERENTLY across VATs,
    so a naive gross comparison would falsely report a gap that is pure tax."""
    gross = Decimal("100.00")
    net_de = vat.net_of_tax(gross, vat.lookup_rate("DE").rate)
    net_be = vat.net_of_tax(gross, vat.lookup_rate("BE").rate)
    # Same shelf price, but BE has higher VAT -> lower net. They are NOT equal.
    assert net_de != net_be
    assert net_de == Decimal("84.03")
    assert net_be == Decimal("82.64")


def test_vat_rate_as_fact_is_strings_only():
    fact = vat.lookup_rate("DE").as_fact()
    assert fact["rate"] == "0.19"  # string, not float
    assert set(fact) == {"country", "category", "rate", "source", "as_of"}
