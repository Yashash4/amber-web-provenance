"""Deterministic product extraction tests (JSON-LD, JSON API, OG meta)."""

from __future__ import annotations

from decimal import Decimal

from amber.capture import extract


def test_extract_json_ld_product():
    body = b"""<html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"Amber Hero",
     "gtin13":"4006381333931",
     "offers":{"@type":"Offer","price":"129.99","priceCurrency":"EUR",
               "availability":"https://schema.org/InStock"}}
    </script></head><body>...</body></html>"""
    ex = extract.extract(body)
    assert ex.source == "json-ld"
    assert ex.price == Decimal("129.99")
    assert ex.currency == "EUR"
    assert ex.availability == "IN_STOCK"
    assert ex.gtin == "4006381333931"
    assert ex.name == "Amber Hero"


def test_extract_plain_json_api_body():
    body = (
        b'{"sku":"X","gtin":"4006381333931","price":"109,99",'
        b'"currency":"EUR","availability":"InStock"}'
    )
    ex = extract.extract(body)
    assert ex.source == "json-api"
    assert ex.price == Decimal("109.99")  # EU comma decimal parsed
    assert ex.currency == "EUR"
    assert ex.gtin == "4006381333931"


def test_extract_og_meta_tags():
    body = b"""<html><head>
    <meta property="og:title" content="Amber Hero">
    <meta property="product:price:amount" content="99.50">
    <meta property="product:price:currency" content="EUR">
    <meta property="product:availability" content="out of stock">
    </head></html>"""
    ex = extract.extract(body)
    assert ex.source == "og-meta"
    assert ex.price == Decimal("99.50")
    assert ex.currency == "EUR"
    assert ex.availability == "OUT_OF_STOCK"


def test_extract_missing_price_is_none_never_zero():
    ex = extract.extract(b"<html><body>no product here</body></html>")
    assert ex.price is None
    assert ex.currency is None
    assert ex.gtin is None
    assert ex.source == "none"


def test_extract_thousands_separators():
    # US style 1,299.00 and EU style 1.299,00 both -> 1299.00
    assert extract._parse_decimal("1,299.00") == Decimal("1299.00")
    assert extract._parse_decimal("1.299,00") == Decimal("1299.00")
    assert extract._parse_decimal("129.99") == Decimal("129.99")
    assert extract._parse_decimal("129,99") == Decimal("129.99")


def test_extract_unparseable_price_is_none():
    assert extract._parse_decimal("free") is None
    assert extract._parse_decimal("") is None
    assert extract._parse_decimal(None) is None


def test_extract_currency_from_header_when_body_lacks_it():
    body = b'{"price":"50.00","availability":"InStock"}'
    ex = extract.extract(body, {"content-currency": "PLN"})
    assert ex.price == Decimal("50.00")
    assert ex.currency == "PLN"


def test_extract_malformed_json_ld_does_not_crash():
    body = b'<script type="application/ld+json">{not valid</script><body>x</body>'
    ex = extract.extract(body)
    # Falls through to none rather than raising.
    assert ex.price is None
