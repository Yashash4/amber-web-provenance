"""Two-source geo-attribution tests.

Uses REAL RIR-attributable IPs from the bundled snapshot (built from RIPE NCC
delegation data) so attribution is tested against real registry data, not a mock.
"""

from __future__ import annotations

import pytest

from amber.capture import geoattr

# Real RIR-attributable IPs from the committed RIPE snapshot. Skip the whole
# module if the snapshot isn't built (CI without the data file).
_DE_IP = "91.10.0.1"
_FR_IP = "62.4.16.1"


@pytest.fixture(autouse=True)
def _require_snapshot():
    if not geoattr._RIR_TABLE:
        pytest.skip("RIR snapshot not built (run scripts/build_rir_snapshot.py)")


def test_rir_lookup_real_ips():
    assert geoattr.rir_country_for_ip(_DE_IP)[0] == "DE"
    assert geoattr.rir_country_for_ip(_FR_IP)[0] == "FR"


def test_rir_lookup_unknown_ip_returns_none():
    # A US Google IP is not in the EU-only snapshot.
    assert geoattr.rir_country_for_ip("8.8.8.8") == (None, None)
    # A garbage string does not raise.
    assert geoattr.rir_country_for_ip("not-an-ip") == (None, None)


def test_confirmed_when_exit_and_response_agree():
    attr = geoattr.attribute(
        "DE",
        _DE_IP,
        {"content-language": "de-DE"},
        proxy_reported_country="DE",
    )
    assert attr.agreement == "CONFIRMED"
    assert attr.rir_country == "DE"


def test_exit_only_when_no_response_signal():
    attr = geoattr.attribute("DE", _DE_IP, {}, proxy_reported_country="DE")
    assert attr.agreement == "EXIT_ONLY"


def test_conflict_when_exit_ip_country_wrong():
    # Asked for DE but the exit IP is a French range -> CONFLICT.
    attr = geoattr.attribute("DE", _FR_IP, {"content-language": "fr-FR"})
    assert attr.agreement == "CONFLICT"


def test_conflict_when_response_locale_wrong():
    attr = geoattr.attribute(
        "DE", _DE_IP, {"content-language": "fr-FR"}, proxy_reported_country="DE"
    )
    assert attr.agreement == "CONFLICT"
    assert any("Content-Language" in n for n in attr.notes)


def test_currency_pins_non_euro_country():
    # PLN pins Poland; requesting DE with PLN observed -> conflict signal.
    attr = geoattr.attribute(
        "DE", _DE_IP, {}, proxy_reported_country="DE", currency_observed="PLN"
    )
    assert attr.agreement == "CONFLICT"
    assert "PL" in str(attr.notes)


def test_eur_does_not_uniquely_pin_a_country():
    # EUR is consistent with many countries -> it must not, alone, confirm.
    attr = geoattr.attribute(
        "DE", _DE_IP, {}, proxy_reported_country="DE", currency_observed="EUR"
    )
    # Exit agrees, EUR is not a unique pin -> EXIT_ONLY (not CONFIRMED on EUR alone).
    assert attr.agreement == "EXIT_ONLY"
    assert "DE" in attr.currency_consistent_countries


def test_as_fact_structure():
    attr = geoattr.attribute("DE", _DE_IP, {"content-language": "de-DE"})
    fact = attr.as_fact()
    assert fact["source_1_network_exit"]["rir_country"] == "DE"
    assert "source_2_response_geo_signals" in fact
    assert fact["agreement"] in {
        "CONFIRMED", "EXIT_ONLY", "RESPONSE_ONLY", "CONFLICT", "UNATTRIBUTED"
    }
