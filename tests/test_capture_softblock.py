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


# A fully-SERVED product page that merely REFERENCES anti-bot tooling — the
# real-world false-positive observed on the first live MediaMarkt capture: a
# 1.2 MB 200-OK product page behind Cloudflare embeds the
# ``/cdn-cgi/challenge-platform`` script and the bare word "captcha" (privacy
# copy / a reCAPTCHA-enterprise script ref), yet is the genuine product page
# (real schema.org price + GTIN). These weak script/word tokens must NOT, on a
# 200 with real content, force INCONCLUSIVE.
SERVED_PRODUCT_WITH_ANTIBOT_SCRIPTS = (
    b"<html><head>"
    b"<script src='/cdn-cgi/challenge-platform/h/g/scripts/jsd/main.js'></script>"
    b"<script src='https://www.google.com/recaptcha/enterprise.js'></script>"
    b"</head><body>"
    b'<script type="application/ld+json">{"@type":"Product","name":"AirPods 4",'
    b'"gtin13":"0195949689673","offers":{"@type":"Offer","price":"179",'
    b'"priceCurrency":"EUR","availability":"https://schema.org/InStock"}}</script>'
    b"<p>By continuing you accept our cookie and captcha policy.</p>"
    b"<!-- datadome _abck _px akamai imperva tokens in markup -->"
    b"</body></html>"
)


def test_served_product_page_referencing_antibot_tooling_is_not_soft_blocked():
    r = softblock.detect(200, {"content-type": "text/html"}, SERVED_PRODUCT_WITH_ANTIBOT_SCRIPTS)
    assert r.is_soft_blocked is False, r.signals
    # No PRIMARY signal -> no weak markers recorded either (they corroborate only).
    assert r.signals == []


def test_weak_marker_corroborates_only_when_a_block_status_is_present():
    # The SAME weak tokens, now on a 403 block, ARE recorded as corroboration.
    r = softblock.detect(403, {}, SERVED_PRODUCT_WITH_ANTIBOT_SCRIPTS)
    assert r.is_soft_blocked is True
    assert "http_status=403" in r.signals
    assert any(s.startswith("weak-body-marker:") for s in r.signals)
