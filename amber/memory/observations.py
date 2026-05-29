"""Deterministic Layer-1 -> memory-observation mapping.

A signed Amber packet's ``facts.json`` (the ``amber/facts@2`` floor schema) is
parsed here into a small, structured :class:`Observation` — the legally- and
financially-relevant slice that the memory graph remembers across captures:

  * the SKU identity (label, canonical GTIN, identity confidence),
  * the country pair,
  * the per-country net-of-tax price (the deterministic, VAT-corrected figure),
  * the cross-country net-of-tax delta + which country is dearer,
  * the within-country control verdict (does the gap survive multiple distinct
    in-country residential exits?),
  * the capture timestamp(s) — the REAL dispatch/witness instants, never invented,
  * the residential exits / RIR registries that witnessed it.

This is pure parsing of already-signed deterministic facts. It contains NO LLM,
fabricates NOTHING (a missing field stays ``None``; it is never defaulted to a
plausible-looking value), and does not import the Phase-1 signing core. Every
number it surfaces was computed deterministically by the Component-2 floor and
committed inside the Merkle-sealed ``facts.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

FACTS_FILENAME = "facts.json"
SUPPORTED_SCHEMA_PREFIX = "amber/facts@2"


class FactsParseError(ValueError):
    """The packet's facts.json is missing, unreadable, or an unsupported schema."""


@dataclass(frozen=True)
class CaptureObservation:
    """One residential capture's memory-relevant slice (no fabrication)."""

    capture_id: str
    country: str
    exit_ip: str | None
    rir_country: str | None
    rir_registry: str | None
    geo_agreement: str | None
    net_price: str | None  # net-of-tax, the VAT-corrected deterministic figure
    gross_price: str | None
    currency: str | None
    state: str | None  # PURCHASABLE / GEO_BLOCKED / INCONCLUSIVE / ...
    session_id: str | None


@dataclass(frozen=True)
class Observation:
    """The memory-graph view of one signed packet (one capture event in time).

    A single packet is ONE point in the SKU's price-gap history. The temporal
    graph remembers a sequence of these; the persistence analysis
    (:mod:`amber.memory.persistence`) reasons over the sequence.
    """

    packet_id: str  # the packet directory name (stable id for this capture event)
    schema: str
    sku_label: str | None
    canonical_gtin: str | None
    sku_identity_confidence: str | None
    countries: tuple[str, ...]
    primary_finding: str | None
    # The net-of-tax cross-country gap, exactly as the deterministic floor sealed it:
    net_of_tax_delta: str | None
    gross_delta: str | None
    more_expensive_country: str | None
    cheaper_country: str | None
    more_expensive_net: str | None
    cheaper_net: str | None
    delta_is_nonzero: bool | None
    # Did the gap survive multiple distinct in-country residential exits?
    within_country_all_agree: bool | None
    # The REAL capture instants (never invented). dispatched_* is the
    # same-second dispatch evidence; witnessed_* are the response timestamps.
    dispatched_same_second: bool | None
    dispatched_at_values: tuple[str, ...]
    witnessed_at_values: tuple[str, ...]
    # The single canonical instant we hang this observation on the timeline by
    # (the earliest real timestamp available; never synthesized).
    observed_at: str | None
    captures: tuple[CaptureObservation, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["countries"] = list(self.countries)
        d["dispatched_at_values"] = list(self.dispatched_at_values)
        d["witnessed_at_values"] = list(self.witnessed_at_values)
        d["captures"] = [asdict(c) for c in self.captures]
        return d


def _earliest_timestamp(*groups: tuple[str, ...]) -> str | None:
    """Pick the earliest REAL ISO timestamp across the supplied groups.

    Returns None if no timestamp exists — we never synthesize one. ISO-8601 in
    the ``...Z`` shape sorts lexicographically, so a plain min() is correct.
    """
    candidates = [t for group in groups for t in group if t]
    return min(candidates) if candidates else None


def observation_from_facts(facts: dict[str, Any], *, packet_id: str) -> Observation:
    """Map a parsed ``amber/facts@2`` dict into an :class:`Observation`.

    Raises :class:`FactsParseError` for an unsupported schema. Missing optional
    fields stay ``None`` — never defaulted to a fabricated value.
    """
    schema = str(facts.get("schema", ""))
    if not schema.startswith(SUPPORTED_SCHEMA_PREFIX):
        raise FactsParseError(
            f"unsupported facts schema {schema!r}; expected {SUPPORTED_SCHEMA_PREFIX!r}"
        )

    sku_identity = facts.get("sku_identity") or {}
    cross = facts.get("cross_country_comparison") or {}
    net_delta = cross.get("net_delta") or {}
    within = facts.get("within_country_control") or {}

    dispatched = tuple(str(t) for t in (facts.get("dispatched_at_values") or []) if t)
    witnessed = tuple(str(t) for t in (facts.get("requested_at_values") or []) if t)

    captures: list[CaptureObservation] = []
    for cap in facts.get("per_capture") or []:
        geo = cap.get("geo_attribution") or {}
        src1 = geo.get("source_1_network_exit") or {}
        state = cap.get("state") or {}
        extracted = cap.get("extracted") or {}
        captures.append(
            CaptureObservation(
                capture_id=str(cap.get("capture_id")) if cap.get("capture_id") else "",
                country=str(cap.get("requested_country")) if cap.get("requested_country") else "",
                exit_ip=cap.get("exit_ip"),
                rir_country=src1.get("rir_country"),
                rir_registry=src1.get("rir_registry"),
                geo_agreement=geo.get("agreement"),
                net_price=cap.get("price_net"),
                gross_price=cap.get("price_gross"),
                currency=extracted.get("currency"),
                state=state.get("state"),
                session_id=cap.get("session_id"),
            )
        )

    return Observation(
        packet_id=packet_id,
        schema=schema,
        sku_label=facts.get("sku_label"),
        canonical_gtin=sku_identity.get("canonical_gtin"),
        sku_identity_confidence=sku_identity.get("confidence"),
        countries=tuple(str(c) for c in (facts.get("countries") or [])),
        primary_finding=cross.get("primary_finding"),
        net_of_tax_delta=net_delta.get("net_of_tax_delta"),
        gross_delta=net_delta.get("gross_delta"),
        more_expensive_country=net_delta.get("more_expensive_country"),
        cheaper_country=net_delta.get("cheaper_country"),
        more_expensive_net=net_delta.get("more_expensive_net"),
        cheaper_net=net_delta.get("cheaper_net"),
        delta_is_nonzero=net_delta.get("delta_is_nonzero"),
        within_country_all_agree=within.get("all_intra_country_agree"),
        dispatched_same_second=facts.get("dispatched_same_second"),
        dispatched_at_values=dispatched,
        witnessed_at_values=witnessed,
        observed_at=_earliest_timestamp(dispatched, witnessed),
        captures=tuple(captures),
    )


def load_facts(packet_dir: Path) -> dict[str, Any]:
    """Read + parse a packet's ``facts.json`` (read-only; never mutates the packet)."""
    facts_path = packet_dir / FACTS_FILENAME
    if not facts_path.exists():
        raise FactsParseError(f"no {FACTS_FILENAME} in {packet_dir}")
    try:
        return json.loads(facts_path.read_bytes().decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise FactsParseError(f"could not parse {facts_path}: {exc}") from exc


def observation_from_packet(packet_dir: Path) -> Observation:
    """Read a sealed packet dir (read-only) and return its :class:`Observation`."""
    facts = load_facts(packet_dir)
    return observation_from_facts(facts, packet_id=packet_dir.name)
