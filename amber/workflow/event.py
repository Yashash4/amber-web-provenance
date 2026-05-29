"""Deterministic event extraction from a signed Amber Layer-1 ``facts.json``.

This module reads ONLY the deterministic, already-signed Layer-1 facts (the
``cross_country_comparison`` block produced by ``amber/capture/floor.py``) and
decides, with no LLM and no fabrication, whether a watched SKU's signed
observation constitutes a workflow-worthy EVENT:

  * ``NET_OF_TAX_PRICE_DELTA`` whose net-of-tax delta is **above a threshold**, or
  * ``ACCESS_OR_PAYMENT_DENIAL`` (one country GEO_BLOCKED while another is
    PURCHASABLE).

The threshold is a workflow-config knob (the brand sets "alert me when the
net-of-tax gap exceeds €X"), NOT a legal/published number — it never appears on
a signed surface and is never characterised as a "violation". Money is compared
with :class:`decimal.Decimal` to avoid float drift, mirroring the floor's own
Decimal arithmetic.

No value here is written back into the packet; this is a read-only derivation
of the signed facts into a workflow event.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# Finding tokens emitted by amber/capture/floor.py::cross_country_comparison.
FINDING_NET_DELTA = "NET_OF_TAX_PRICE_DELTA"
FINDING_ACCESS_DENIAL = "ACCESS_OR_PAYMENT_DENIAL"
FINDING_NO_DELTA = "NO_NET_DELTA"
FINDING_INCONCLUSIVE = "INCONCLUSIVE"

# Event kinds Amber raises into a workflow.
KIND_NET_DELTA = "NET_OF_TAX_PRICE_DELTA"
KIND_ACCESS_DENIAL = "ACCESS_OR_PAYMENT_DENIAL"

# Default threshold (EUR, net of tax) above which a price delta becomes an event.
# A small positive default so a 0.00 control never fires; overridable per-call.
DEFAULT_NET_DELTA_THRESHOLD_EUR = Decimal("1.00")


class NoEventError(RuntimeError):
    """The signed facts contain no workflow-worthy event (no false events)."""


def _to_decimal(value: Any) -> Decimal:
    """Parse a money string/number to Decimal, raising on garbage (never 0-default)."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:  # surface, never swallow
        raise ValueError(f"not a decimal money value: {value!r}") from exc


@dataclass(frozen=True)
class EventThreshold:
    """Workflow threshold config — the brand's alert knob, not a legal number."""

    net_delta_eur: Decimal = DEFAULT_NET_DELTA_THRESHOLD_EUR

    @classmethod
    def from_eur(cls, amount: str | float | Decimal) -> EventThreshold:
        return cls(net_delta_eur=_to_decimal(amount))


@dataclass(frozen=True)
class AmberEvent:
    """A workflow event derived deterministically from signed Layer-1 facts.

    Carries only the signed facts relevant to the workflow decision plus the
    operator's threshold context. It deliberately states a FACT, never a verdict
    — there is no "violation" field and the legal characterisation lives only in
    the separate, unsigned Layer-2 jury advisory.
    """

    kind: str
    sku_label: str
    countries: tuple[str, ...]
    # Net-of-tax delta facts (present for KIND_NET_DELTA).
    net_of_tax_delta_eur: Decimal | None
    gross_delta_eur: Decimal | None
    cheaper_country: str | None
    more_expensive_country: str | None
    cheaper_net_eur: Decimal | None
    more_expensive_net_eur: Decimal | None
    # Access/payment-denial facts (present for KIND_ACCESS_DENIAL).
    geo_blocked_countries: tuple[str, ...]
    purchasable_countries: tuple[str, ...]
    # Provenance / context (all from the signed facts, never invented).
    within_country_control_agree: bool | None
    sku_identity_confidence: str | None
    dispatched_same_second: bool | None
    same_second_batch: bool | None
    threshold_eur: Decimal
    # The signed-FACT banner line (states the fact; never "violation").
    fact_banner: str = field(default="")

    def as_row(self) -> dict[str, Any]:
        """A flat, SQL-friendly row of the event (Decimals -> strings).

        This is the row Amber pushes to TriggerWare's queryable API and over
        which the trigger's SQL predicate evaluates. Money is serialised as a
        fixed-point string so the round-trip is lossless.
        """

        def money(d: Decimal | None) -> str | None:
            return format(d, "f") if d is not None else None

        return {
            "sku_label": self.sku_label,
            "kind": self.kind,
            "countries": ",".join(self.countries),
            "net_of_tax_delta_eur": money(self.net_of_tax_delta_eur),
            "gross_delta_eur": money(self.gross_delta_eur),
            "cheaper_country": self.cheaper_country,
            "more_expensive_country": self.more_expensive_country,
            "cheaper_net_eur": money(self.cheaper_net_eur),
            "more_expensive_net_eur": money(self.more_expensive_net_eur),
            "geo_blocked_countries": ",".join(self.geo_blocked_countries) or None,
            "purchasable_countries": ",".join(self.purchasable_countries) or None,
            "within_country_control_agree": self.within_country_control_agree,
            "sku_identity_confidence": self.sku_identity_confidence,
            "dispatched_same_second": self.dispatched_same_second,
            "same_second_batch": self.same_second_batch,
            "threshold_eur": format(self.threshold_eur, "f"),
            "fact_banner": self.fact_banner,
        }

    def as_dict(self) -> dict[str, Any]:
        """Full event payload (row + a machine-readable derivation note)."""
        return {
            "schema": "amber/workflow_event@1",
            "derived_from": "signed Layer-1 facts.json (cross_country_comparison)",
            "event": self.as_row(),
            "note": (
                "Deterministic derivation of the signed Layer-1 facts; no LLM, "
                "no fabricated value. Stated as a FACT, not a legal verdict. The "
                "threshold is the operator's alert knob, not a legal number."
            ),
        }


def load_facts(packet_dir: Path | str) -> dict[str, Any]:
    """Load a sealed packet's ``facts.json`` (read-only; never mutates it)."""
    pdir = Path(packet_dir)
    if not pdir.is_dir():
        raise NoEventError(f"not a packet directory: {pdir}")
    facts_path = pdir / "facts.json"
    if not facts_path.exists():
        raise NoEventError(f"no facts.json in packet: {pdir}")
    return json.loads(facts_path.read_bytes().decode("utf-8"))


def _within_country_agree(facts: dict[str, Any]) -> bool | None:
    wcc = facts.get("within_country_control")
    if isinstance(wcc, dict) and "all_intra_country_agree" in wcc:
        return bool(wcc["all_intra_country_agree"])
    return None


def _sku_identity_confidence(facts: dict[str, Any]) -> str | None:
    ident = facts.get("sku_identity")
    if isinstance(ident, dict):
        c = ident.get("confidence")
        return str(c) if c is not None else None
    return None


def _build_net_delta_banner(more_expensive: str, cheaper: str, delta: Decimal) -> str:
    return (
        f"PRICE DELTA DETECTED — signed, net-of-tax, chain of custody: "
        f"{more_expensive} net €{format(delta, 'f')} higher than {cheaper}"
    )


def _build_denial_banner(blocked: tuple[str, ...], purchasable: tuple[str, ...]) -> str:
    return (
        "ACCESS/PAYMENT DENIAL DETECTED — signed, ≥2 causally-independent "
        f"signals, chain of custody: {'/'.join(blocked)} blocked while "
        f"{'/'.join(purchasable)} purchasable"
    )


def extract_event(
    facts: dict[str, Any],
    threshold: EventThreshold | None = None,
) -> AmberEvent:
    """Derive a workflow event from signed Layer-1 facts, applying the threshold.

    Raises :class:`NoEventError` when the signed facts hold no event above the
    threshold (a sub-threshold delta, a net-of-tax control that agrees, or an
    inconclusive observation) — Amber never invents an event that the signed
    facts do not support.
    """
    threshold = threshold or EventThreshold()
    comp = facts.get("cross_country_comparison")
    if not isinstance(comp, dict):
        raise NoEventError("facts.json has no cross_country_comparison block")

    primary = comp.get("primary_finding")
    sku_label = str(facts.get("sku_label") or "unknown SKU")
    countries = tuple(facts.get("countries") or [])
    common = {
        "sku_label": sku_label,
        "countries": countries,
        "within_country_control_agree": _within_country_agree(facts),
        "sku_identity_confidence": _sku_identity_confidence(facts),
        "dispatched_same_second": facts.get("dispatched_same_second"),
        "same_second_batch": facts.get("same_second_batch"),
        "threshold_eur": threshold.net_delta_eur,
    }

    # Access/payment denial is the strongest finding and takes precedence.
    if primary == FINDING_ACCESS_DENIAL:
        denial = comp.get("access_denial") or {}
        blocked = tuple(denial.get("geo_blocked_countries") or [])
        purchasable = tuple(denial.get("purchasable_countries") or [])
        return AmberEvent(
            kind=KIND_ACCESS_DENIAL,
            net_of_tax_delta_eur=None,
            gross_delta_eur=None,
            cheaper_country=None,
            more_expensive_country=None,
            cheaper_net_eur=None,
            more_expensive_net_eur=None,
            geo_blocked_countries=blocked,
            purchasable_countries=purchasable,
            fact_banner=_build_denial_banner(blocked, purchasable),
            **common,
        )

    if primary == FINDING_NET_DELTA:
        nd = comp.get("net_delta") or {}
        delta = _to_decimal(nd["net_of_tax_delta"])
        if delta <= threshold.net_delta_eur:
            raise NoEventError(
                f"net-of-tax delta €{format(delta, 'f')} does not exceed the "
                f"threshold €{format(threshold.net_delta_eur, 'f')}; no event"
            )
        gross_delta = (
            _to_decimal(nd["gross_delta"]) if nd.get("gross_delta") is not None else None
        )
        cheaper = nd.get("cheaper_country")
        expensive = nd.get("more_expensive_country")
        return AmberEvent(
            kind=KIND_NET_DELTA,
            net_of_tax_delta_eur=delta,
            gross_delta_eur=gross_delta,
            cheaper_country=cheaper,
            more_expensive_country=expensive,
            cheaper_net_eur=_to_decimal(nd["cheaper_net"]),
            more_expensive_net_eur=_to_decimal(nd["more_expensive_net"]),
            geo_blocked_countries=(),
            purchasable_countries=(),
            fact_banner=_build_net_delta_banner(expensive, cheaper, delta),
            **common,
        )

    # NO_NET_DELTA / INCONCLUSIVE / anything else -> no event (honest restraint).
    raise NoEventError(
        f"no workflow-worthy event in signed facts (primary_finding={primary!r})"
    )
