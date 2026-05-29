"""Anti-bot / soft-block detector tests — the credibility gate."""

from __future__ import annotations

import pytest

from amber.capture import softblock

CLOUDFLARE_CHALLENGE = (
    b"<html><head><title>Just a moment...</title></head><body>"
    b"<div class='cf-challenge'>Verifying you are human. "
    b"<script src='/cdn-cgi/challenge-platform/h/b/orchestrate'></script>"
    b"</div></body></html>"
)

CAPTCHA_PAGE = (
    b"<html><body><form><div class='g-recaptcha'></div>"
    b"Please complete the captcha to continue.</body></html>"
)

# A genuine product page that should NOT be flagged.
CLEAN_PRODUCT = (
    b'{"sku":"X","gtin":"4006381333931","price":"129.99","currency":"EUR",'
    b'"availability":"InStock","description":"a normal product body with enough '
    b'bytes to exceed the degenerate threshold and look like a real response"}'
)


def test_cloudflare_challenge_is_soft_blocked():
    r = softblock.detect(200, {"server": "cloudflare"}, CLOUDFLARE_CHALLENGE)
    assert r.is_soft_blocked is True
    assert any("body-marker" in s for s in r.signals)


def test_captcha_page_is_soft_blocked():
    r = softblock.detect(200, {}, CAPTCHA_PAGE)
    assert r.is_soft_blocked is True
    assert any("captcha" in s for s in r.signals)


@pytest.mark.parametrize("status", [429, 403, 503])
def test_throttle_status_is_soft_blocked(status):
    r = softblock.detect(status, {"retry-after": "30"}, b"slow down")
    assert r.is_soft_blocked is True
    assert f"http_status={status}" in r.signals


def test_clean_product_is_not_soft_blocked():
    r = softblock.detect(200, {"content-type": "application/json"}, CLEAN_PRODUCT)
    assert r.is_soft_blocked is False
    assert r.signals == []


def test_datadome_header_marker():
    r = softblock.detect(200, {"x-datadome": "protected"}, b"some body content here")
    assert r.is_soft_blocked is True
    assert any("x-datadome" in s for s in r.signals)


def test_tiny_clean_body_alone_is_not_a_block():
    # A small legit JSON API body with no other signal must NOT be flagged.
    r = softblock.detect(200, {"content-type": "application/json"}, b'{"ok":true}')
    assert r.is_soft_blocked is False


def test_geo_reason_text_detected_but_separate_from_softblock():
    body = b"<html><body>This item is not available in your country.</body></html>"
    assert softblock.detect_geo_reason_text(body) is not None
    # The clean (non-challenge) page is NOT a soft-block; geo-reason is a separate
    # candidate signal handled by state.py.
    assert softblock.detect(200, {}, body).is_soft_blocked is False


def test_geo_reason_text_on_challenge_page_still_softblocked():
    body = CAPTCHA_PAGE + b"not available in your region"
    assert softblock.detect(200, {}, body).is_soft_blocked is True
