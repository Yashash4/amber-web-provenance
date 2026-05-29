"""Amber Component 2 — Bright Data residential capture + the deterministic
measurement-validity floor that produces the Layer-1 facts.

This package is the *fetcher + geo-witness* layer. It captures the SAME product
URL from multiple EU countries (Germany, Belgium) plus a within-country control
(several distinct residential exits per country) in a same-second batch, then
derives the **deterministic, no-LLM Layer-1 facts** (net-of-tax spread, GTIN /
SKU-identity confidence, per-geo factual state with the GEO_BLOCKED >=2-signal
floor, two-source geo-attribution, and the within-country control result) and
feeds the raw bodies + ``facts.json`` into Component 1's :func:`amber.packet.seal_packet`.

NOTHING in this package uses an LLM, and nothing here fabricates a price, a
country, or history. The capture client talks to real Bright Data residential
exits; the floor computes facts only from bytes that were actually captured.
"""

from __future__ import annotations

__all__ = [
    "vat",
    "geoattr",
    "softblock",
    "state",
    "identity",
    "extract",
    "floor",
    "brightdata",
    "harness",
    "discover",
]
