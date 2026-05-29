"""Deterministic extraction of product facts from a captured response body.

Pulls price, currency, availability, GTIN, name, and explicit access/payment
denial signals out of the raw bytes — **deterministically, no LLM**. The
extractor understands the structured surfaces a real product page exposes, in
priority order:

  1. schema.org JSON-LD ``Product``/``Offer`` blocks (the canonical, machine-
     readable surface — ``price``, ``priceCurrency``, ``availability``, ``gtin*``).
  2. Open Graph / product meta tags (``og:price:amount`` etc.).
  3. A plain JSON API body (the shape many SPA product endpoints return, and the
     shape the unit-test fixtures use): top-level or nested ``price`` / ``gtin`` /
     ``availability`` keys.

Everything returned is exactly what was present in the bytes. If a field is
absent it is ``None`` — never inferred, never defaulted. A missing price does not
become 0; a missing GTIN does not fall back to the product name. That restraint
is what makes the downstream facts defensible.

Prices are returned as :class:`~decimal.Decimal` (parsed from the textual
representation) so there is no float drift in the signed figure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# schema.org availability URLs / tokens -> a normalized availability token.
_SCHEMA_AVAILABILITY = {
    "instock": "IN_STOCK",
    "in_stock": "IN_STOCK",
    "outofstock": "OUT_OF_STOCK",
    "out_of_stock": "OUT_OF_STOCK",
    "soldout": "OUT_OF_STOCK",
    "discontinued": "DISCONTINUED",
    "preorder": "PREORDER",
    "backorder": "BACKORDER",
    "limitedavailability": "LIMITED",
    "onlineonly": "IN_STOCK",
    "instoreonly": "IN_STORE_ONLY",
}

# GTIN keys we recognise in JSON-LD / JSON bodies (schema.org uses several).
_GTIN_KEYS = ("gtin", "gtin13", "gtin12", "gtin8", "gtin14", "ean", "upc")

_PRICE_CLEAN = re.compile(r"[^0-9.,\-]")


@dataclass
class Extracted:
    """The deterministically extracted product facts from one body.

    All fields are exactly-as-present-or-None. ``source`` names which surface the
    primary price came from (``json-ld`` / ``og-meta`` / ``json-api`` / ``none``)
    so the fact is auditable.
    """

    price: Decimal | None = None
    currency: str | None = None
    availability: str | None = None  # normalized token, see _SCHEMA_AVAILABILITY
    gtin: str | None = None
    name: str | None = None
    source: str = "none"
    raw_signals: dict[str, str] = field(default_factory=dict)

    def as_fact(self) -> dict:
        return {
            "price": format(self.price, "f") if self.price is not None else None,
            "currency": self.currency,
            "availability": self.availability,
            "gtin": self.gtin,
            "name": self.name,
            "source": self.source,
            "raw_signals": dict(self.raw_signals),
        }


def _parse_decimal(value: object) -> Decimal | None:
    """Parse a price-ish value into Decimal, handling EU/US separators.

    Accepts ``"129.99"``, ``"129,99"``, ``"1.299,00"``, ``"1,299.00"``,
    ``129.99`` (number). Returns ``None`` on anything unparseable — never 0.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # A JSON number: stringify via repr to avoid binary-float artifacts where
        # possible, then Decimal. (Most real product JSON sends price as a string;
        # this branch is defensive.)
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    s = _PRICE_CLEAN.sub("", s)
    if not s or s in {"-", ".", ","}:
        return None
    # Decide decimal separator: if both '.' and ',' appear, the LAST one is the
    # decimal separator (handles 1.299,00 and 1,299.00); strip the other.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Only commas: treat as decimal separator if it looks like cents, else
        # thousands. Heuristic: if exactly 2 digits follow the last comma -> decimal.
        if re.search(r",\d{2}$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _normalize_availability(value: object) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower()
    # schema.org often gives a URL like https://schema.org/InStock
    token = token.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    token = token.replace(" ", "").replace("-", "")
    return _SCHEMA_AVAILABILITY.get(token)


def _normalize_gtin(value: object) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\D", "", str(value))
    return s or None


def _walk_json_for_product(obj: object) -> dict | None:
    """Find the first dict that looks like a schema.org Product/Offer.

    Recurses through lists/dicts. A node is a product candidate if it has a
    ``@type`` of Product/Offer (case-insensitive) OR it carries a price key. The
    first such node wins (deterministic depth-first order).
    """
    if isinstance(obj, dict):
        typ = str(obj.get("@type", "")).lower()
        if typ in {"product", "offer", "aggregateoffer"} or "price" in obj or any(
            k in obj for k in _GTIN_KEYS
        ):
            return obj
        for v in obj.values():
            found = _walk_json_for_product(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _walk_json_for_product(item)
            if found is not None:
                return found
    return None


_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
    re.I,
)


def _extract_from_product_dict(node: dict) -> Extracted:
    ex = Extracted(source="json")
    # Price + currency can live on the node or a nested "offers".
    offers = node.get("offers")
    price_node: dict = node
    if isinstance(offers, dict):
        price_node = offers
    elif isinstance(offers, list) and offers and isinstance(offers[0], dict):
        price_node = offers[0]

    ex.price = _parse_decimal(price_node.get("price"))
    cur = price_node.get("priceCurrency") or price_node.get("currency")
    ex.currency = str(cur).upper() if cur else None
    ex.availability = _normalize_availability(
        price_node.get("availability") or node.get("availability")
    )
    for k in _GTIN_KEYS:
        if node.get(k):
            ex.gtin = _normalize_gtin(node.get(k))
            break
    name = node.get("name")
    ex.name = str(name) if name else None
    return ex


def extract(body: bytes, headers: dict[str, str] | None = None) -> Extracted:
    """Deterministically extract product facts from a captured body.

    Tries, in order: JSON-LD inside HTML, a plain JSON body, OG/meta tags. The
    FIRST surface that yields a price (or, failing that, any product node) wins;
    its ``source`` is recorded. Header-level currency hints fill currency only if
    the body had none. Never raises on malformed input — a body it cannot parse
    yields an empty :class:`Extracted` (all ``None``), which the floor treats as
    INCONCLUSIVE, not as a fabricated value.
    """
    headers = headers or {}
    text = body.decode("utf-8", errors="replace")

    # 1. JSON-LD blocks embedded in HTML.
    for m in _JSONLD_RE.finditer(text):
        chunk = m.group(1).strip()
        try:
            data = json.loads(chunk)
        except (ValueError, json.JSONDecodeError):
            continue
        node = _walk_json_for_product(data)
        if node is not None:
            ex = _extract_from_product_dict(node)
            ex.source = "json-ld"
            if ex.price is not None or ex.gtin is not None or ex.availability is not None:
                _fill_currency_from_headers(ex, headers)
                return ex

    # 2. Plain JSON body (SPA product API / the test fixtures).
    stripped = text.strip()
    if stripped[:1] in "{[":
        try:
            data = json.loads(stripped)
        except (ValueError, json.JSONDecodeError):
            data = None
        if data is not None:
            node = _walk_json_for_product(data)
            if node is not None:
                ex = _extract_from_product_dict(node)
                ex.source = "json-api"
                _fill_currency_from_headers(ex, headers)
                return ex

    # 3. Open Graph / product meta tags in HTML.
    meta: dict[str, str] = {}
    for prop, content in _META_RE.findall(text):
        meta[prop.lower()] = content
    if meta:
        ex = Extracted(source="og-meta", raw_signals=meta)
        ex.price = _parse_decimal(
            meta.get("product:price:amount") or meta.get("og:price:amount")
        )
        cur = meta.get("product:price:currency") or meta.get("og:price:currency")
        ex.currency = str(cur).upper() if cur else None
        avail = meta.get("product:availability") or meta.get("og:availability")
        ex.availability = _normalize_availability(avail)
        ex.name = meta.get("og:title")
        if ex.price is not None:
            _fill_currency_from_headers(ex, headers)
            return ex

    # Nothing parseable -> all-None (the floor will record INCONCLUSIVE).
    empty = Extracted(source="none")
    _fill_currency_from_headers(empty, headers)
    return empty


def _fill_currency_from_headers(ex: Extracted, headers: dict[str, str]) -> None:
    """If the body had no currency, take an explicit currency header (only)."""
    if ex.currency:
        return
    lower = {k.lower(): v for k, v in headers.items()}
    for h in ("content-currency", "x-currency"):
        if lower.get(h):
            ex.currency = str(lower[h]).upper()
            return
