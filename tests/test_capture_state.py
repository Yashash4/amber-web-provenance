"""Factual-state classifier tests — the GEO_BLOCKED >=2-signal floor + soft-block
forcing INCONCLUSIVE are the load-bearing rules."""

from __future__ import annotations

from amber.capture import extract, softblock, state


def _classify(status, headers, body):
    ex = extract.extract(body, headers)
    sb = softblock.detect(status, headers, body)
    return state.classify(status, headers, body, ex, sb)


PRODUCT_IN_STOCK = (
    b'{"gtin":"4006381333931","price":"129.99","currency":"EUR","availability":"InStock"}'
)
PRODUCT_OOS = (
    b'{"gtin":"4006381333931","price":"129.99","currency":"EUR","availability":"OutOfStock"}'
)


def test_purchasable():
    r = _classify(200, {"content-type": "application/json"}, PRODUCT_IN_STOCK)
    assert r.state == state.PURCHASABLE


def test_out_of_stock():
    r = _classify(200, {}, PRODUCT_OOS)
    assert r.state == state.OUT_OF_STOCK


def test_single_geo_signal_is_inconclusive_not_geo_blocked():
    """One geo-reason signal alone must NOT promote to GEO_BLOCKED (the >=2 floor)."""
    body = b"<html><body>This product is not available in your country.</body></html>"
    r = _classify(200, {}, body)
    assert r.state == state.INCONCLUSIVE
    assert len(r.geo_block_signals) == 1
    assert "do NOT auto-promote" in r.rationale


def test_two_independent_signals_make_geo_blocked():
    """451 status (class: http_status) + on-page geo-reason (class: dom_geo_reason)
    = two causally-independent classes -> GEO_BLOCKED."""
    body = b"<html><body>We do not ship to your country.</body></html>"
    r = _classify(451, {}, body)
    assert r.state == state.GEO_BLOCKED
    classes = {s.signal_class for s in r.geo_block_signals}
    assert classes == {state.SIGNAL_CLASS_STATUS, state.SIGNAL_CLASS_DOM_REASON}


def test_geo_redirect_plus_status_is_geo_blocked():
    r = _classify(451, {"location": "https://shop.example/geo-blocked"}, b"redirecting")
    assert r.state == state.GEO_BLOCKED
    classes = {s.signal_class for s in r.geo_block_signals}
    assert state.SIGNAL_CLASS_REDIRECT in classes
    assert state.SIGNAL_CLASS_STATUS in classes


def test_softblock_forces_inconclusive_even_with_geo_reason_text():
    """THE honesty rule: a CAPTCHA page that ALSO contains geo-reason text must be
    INCONCLUSIVE, never GEO_BLOCKED — the geo text is discarded."""
    body = (
        b"<html><body><div class='g-recaptcha'></div>"
        b"This product is not available in your country.</body></html>"
    )
    r = _classify(200, {}, body)
    assert r.state == state.INCONCLUSIVE
    assert r.soft_block.is_soft_blocked is True
    assert "disregarded" in r.rationale
    # No GEO_BLOCKED signals were even collected.
    assert r.geo_block_signals == []


def test_softblock_status_forces_inconclusive():
    body = b"<html><body>not available in your region</body></html>"
    r = _classify(403, {}, body)  # 403 is a soft-block status
    assert r.state == state.INCONCLUSIVE


def test_price_gated():
    body = b"<html><body>Log in to see price for this product.</body></html>"
    r = _classify(200, {}, body)
    assert r.state == state.PRICE_GATED


def test_not_sold_here_non_blocking():
    body = b"<html><body>This product is not carried in this store for your area.</body></html>"
    # phrase below matches a NOT_SOLD_HERE marker, no access refusal
    body = b"<html><body>not part of our assortment in this market</body></html>"
    r = _classify(200, {}, body)
    assert r.state == state.NOT_SOLD_HERE


def test_empty_body_is_inconclusive_not_a_guess():
    r = _classify(200, {}, b"")
    assert r.state == state.INCONCLUSIVE


def test_two_facets_of_same_cause_do_not_double_count():
    """Two geo-reason phrases (same causal class) must NOT count as 2 signals."""
    body = (
        b"<html><body>not available in your country. "
        b"we do not ship to your location.</body></html>"
    )
    r = _classify(200, {}, body)
    # Both phrases are SIGNAL_CLASS_DOM_REASON -> collapsed to one class -> 1 signal.
    assert len(r.geo_block_signals) == 1
    assert r.state == state.INCONCLUSIVE
