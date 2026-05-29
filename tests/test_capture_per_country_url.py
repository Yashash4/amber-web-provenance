"""Per-country-URL batch tests (the domain-per-country storefront case).

The intra-EU norm is often a SAME GTIN sold on two ccTLD storefronts
(``mediamarkt.de`` vs ``mediamarkt.be``), not one geo-IP-gated URL. These tests
exercise :func:`brightdata.same_second_batch_per_country_url` and the
single-URL wrapper that now delegates to it — with ``capture_one`` monkeypatched
(no network) so we assert: each country fetched ITS OWN URL, every per-country
session got a distinct in-country exit (the within-country control), and the
single-URL wrapper still fetches the one URL for every country.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from amber.capture import brightdata
from amber.capture.credentials import BrightDataCredentials
from amber.capture.record import CaptureRecord

CREDS = BrightDataCredentials(
    mode="proxy", customer_id="c", zone="z", password="p"
)

# Distinct in-country residential exits keyed by (country, session-index).
_EXITS = {
    ("DE", 0): "89.1.219.154",
    ("DE", 1): "92.208.62.108",
    ("DE", 2): "84.150.0.7",
    ("BE", 0): "91.178.196.100",
    ("BE", 1): "94.224.0.9",
    ("BE", 2): "81.241.0.3",
}


@pytest.fixture
def fake_capture_one(monkeypatch: pytest.MonkeyPatch):
    """Replace the network capture with a deterministic record + instant.

    Records the URL it was asked to fetch so the test can assert per-country
    routing; hands back a distinct exit IP per (country, session) so the
    within-country control sees distinct exits.
    """
    seen: list[tuple[str, str, str]] = []  # (country, session, url)
    counters: dict[str, int] = {}

    def _fake(creds, url, country, session, capture_id, *, timeout=45):
        idx = counters.get(country, 0)
        counters[country] = idx + 1
        seen.append((country, session, url))
        rec = CaptureRecord(
            capture_id=capture_id,
            url=url,
            requested_country=country.upper(),
            session_id=session,
            exit_ip=_EXITS[(country.upper(), idx)],
            requested_at="UNSET",
            http_status=200,
            headers={"content-type": "application/json"},
            body=b'{"gtin":"0195949689673","price":"179","currency":"EUR"}',
        )
        return rec, datetime(2026, 5, 29, 0, 0, 1, tzinfo=UTC)

    monkeypatch.setattr(brightdata, "capture_one", _fake)
    return seen


def test_per_country_url_routes_each_country_to_its_own_url(fake_capture_one):
    country_urls = {
        "DE": "https://www.mediamarkt.de/de/product/airpods-4-anc.html",
        "BE": "https://www.mediamarkt.be/nl/product/airpods-4-anc.html",
    }
    records = brightdata.same_second_batch_per_country_url(CREDS, country_urls, 3)

    assert len(records) == 6
    de = [r for r in records if r.requested_country == "DE"]
    be = [r for r in records if r.requested_country == "BE"]
    assert len(de) == 3 and len(be) == 3
    # Each country fetched its OWN storefront URL on every session.
    assert {r.url for r in de} == {country_urls["DE"]}
    assert {r.url for r in be} == {country_urls["BE"]}
    # The within-country control: 3 DISTINCT in-country residential exits each.
    assert len({r.exit_ip for r in de}) == 3
    assert len({r.exit_ip for r in be}) == 3
    # Same-second batch (all instants identical) -> one canonical second.
    assert len({r.requested_at for r in records}) == 1


def test_single_url_wrapper_delegates_and_fetches_one_url(fake_capture_one):
    url = "https://shop.example/p/geo-gated"
    records = brightdata.same_second_batch(CREDS, url, ["DE", "BE"], 3)
    assert len(records) == 6
    # The geo-IP single-URL case: every capture fetched the SAME url.
    assert {r.url for r in records} == {url}
    assert {(c, s, u) for (c, s, u) in fake_capture_one} == {
        (c, s, url) for (c, s, _u) in fake_capture_one
    }


def test_empty_country_url_map_is_surfaced_not_swallowed():
    with pytest.raises(brightdata.CaptureError):
        brightdata.same_second_batch_per_country_url(CREDS, {}, 3)
