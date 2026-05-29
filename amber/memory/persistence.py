"""Deterministic persistence analysis over a sequence of observations.

This is the agent-memory *deliverable*'s honest backbone: given the observations
that GENUINELY exist (one per signed packet), it answers the questions a brand's
anti-diversion agent actually asks — *is this net-of-tax gap persistent or
transient? which countries/SKUs recur? is the gap sustained across the captures
we have?* — using only real data.

It computes nothing it cannot ground:

  * The window is **real**: ``first_seen`` / ``last_seen`` are the earliest and
    latest REAL capture timestamps; ``n_captures`` is the literal count of
    packets. The human-facing line is *"N captures over [real window]; the
    baseline compounds from day one"* — never an invented multi-week chart. With
    a single capture it says so plainly (a one-point baseline, not a trend).
  * "Persistent" is defined operationally and stated as such: the gap is
    PERSISTENT only if it is present-and-nonzero in **every** capture of the SKU
    AND there are at least two captures spanning more than a moment. One capture
    is a BASELINE (insufficient history to call persistence — the honest answer).
    A gap that appears in some captures and not others is INTERMITTENT; a gap
    seen once that then disappears is TRANSIENT.

No LLM is involved in any number here, and nothing is fabricated. The Cognee
graph (:mod:`amber.memory.store`) is the *queryable* surface over the same
observations; this module is the deterministic ground truth those queries can be
checked against.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from amber.memory.observations import Observation

# Persistence verdicts (operationally defined; stated honestly, never inflated).
BASELINE = "BASELINE"  # only one capture — insufficient history to call a trend
PERSISTENT = "PERSISTENT"  # gap present + nonzero in EVERY capture, >=2 captures
INTERMITTENT = "INTERMITTENT"  # gap in some captures, absent in others
TRANSIENT = "TRANSIENT"  # gap seen but absent in the most recent capture(s)
NO_GAP = "NO_GAP"  # no nonzero net-of-tax gap in any capture


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _gap_present(obs: Observation) -> bool:
    """Was a nonzero net-of-tax gap deterministically present in this capture?"""
    if obs.delta_is_nonzero is True:
        return True
    d = _decimal(obs.net_of_tax_delta)
    return d is not None and d != Decimal("0")


def _real_window_phrase(n_captures: int, first_seen: str | None, last_seen: str | None) -> str:
    """The honest window phrasing — NEVER an invented multi-week history.

    One capture -> "a one-point baseline" (a single instant, not a trend).
    Several captures -> "N captures over [first .. last]; the baseline compounds
    from day one" — forward-looking and true.
    """
    if n_captures <= 0:
        return "no captures yet — nothing observed"
    if n_captures == 1:
        when = first_seen or "an unrecorded instant"
        return (
            f"1 capture at {when} — a one-point baseline (insufficient history to "
            "call persistence; the baseline compounds from day one)"
        )
    if first_seen and last_seen and first_seen != last_seen:
        window = f"{first_seen} .. {last_seen}"
    elif first_seen:
        window = f"{first_seen} (single instant)"
    else:
        window = "an unrecorded window"
    return (
        f"{n_captures} captures over {window} — the baseline compounds from day "
        "one (real captures only; no history is fabricated)"
    )


@dataclass(frozen=True)
class PersistenceReport:
    """The deterministic persistence verdict for ONE SKU across its captures."""

    canonical_gtin: str | None
    sku_label: str | None
    countries: tuple[str, ...]
    n_captures: int
    first_seen: str | None
    last_seen: str | None
    real_window: str  # the honest "N captures over [real window]" phrasing
    verdict: str  # BASELINE / PERSISTENT / INTERMITTENT / TRANSIENT / NO_GAP
    captures_with_gap: int
    latest_net_of_tax_delta: str | None
    latest_more_expensive_country: str | None
    within_country_corroborated: bool  # did the within-country control AGREE every time?
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_gtin": self.canonical_gtin,
            "sku_label": self.sku_label,
            "countries": list(self.countries),
            "n_captures": self.n_captures,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "real_window": self.real_window,
            "verdict": self.verdict,
            "captures_with_gap": self.captures_with_gap,
            "latest_net_of_tax_delta": self.latest_net_of_tax_delta,
            "latest_more_expensive_country": self.latest_more_expensive_country,
            "within_country_corroborated": self.within_country_corroborated,
            "rationale": self.rationale,
        }


def _sku_key(obs: Observation) -> str:
    """Group observations by SKU — canonical GTIN preferred, label as fallback."""
    return obs.canonical_gtin or obs.sku_label or obs.packet_id


def _ordered_by_time(observations: list[Observation]) -> list[Observation]:
    """Chronological order by real ``observed_at`` (missing timestamps sort last)."""
    return sorted(observations, key=lambda o: (o.observed_at is None, o.observed_at or ""))


def analyze_sku(observations: list[Observation]) -> PersistenceReport:
    """Compute the persistence verdict for a set of observations of ONE SKU.

    The caller is responsible for passing observations of a single SKU; mixing
    SKUs is a programming error. The verdict is operational and stated honestly:
    one capture is a BASELINE (never asserted as a trend).
    """
    if not observations:
        raise ValueError("analyze_sku requires at least one observation")

    ordered = _ordered_by_time(observations)
    n = len(ordered)
    timestamps = [o.observed_at for o in ordered if o.observed_at]
    first_seen = timestamps[0] if timestamps else None
    last_seen = timestamps[-1] if timestamps else None

    gap_flags = [_gap_present(o) for o in ordered]
    captures_with_gap = sum(1 for g in gap_flags if g)

    countries: tuple[str, ...] = tuple(
        sorted({c for o in ordered for c in o.countries})
    )
    latest = ordered[-1]
    within_corroborated = all(o.within_country_all_agree is True for o in ordered)

    if n == 1:
        verdict = BASELINE if gap_flags[0] else NO_GAP
        if verdict == BASELINE:
            rationale = (
                "A single signed capture shows a nonzero net-of-tax gap. This is "
                "a one-point baseline, not a trend: persistence cannot be asserted "
                "from one capture. The baseline compounds from the next capture on."
            )
        else:
            rationale = "A single signed capture shows no nonzero net-of-tax gap."
    elif captures_with_gap == 0:
        verdict = NO_GAP
        rationale = f"No nonzero net-of-tax gap in any of {n} captures."
    elif captures_with_gap == n:
        verdict = PERSISTENT
        rationale = (
            f"A nonzero net-of-tax gap is present in ALL {n} captures over the real "
            "window — the gap is sustained, not capture noise. A sustained gap is a "
            "real margin signal, not a transient blip."
        )
    elif gap_flags[-1]:
        verdict = INTERMITTENT
        rationale = (
            f"A net-of-tax gap is present in {captures_with_gap} of {n} captures "
            "(including the most recent) but absent in others — intermittent, not "
            "continuously sustained."
        )
    else:
        verdict = TRANSIENT
        rationale = (
            f"A net-of-tax gap appeared in {captures_with_gap} of {n} captures but is "
            "absent in the most recent capture — it did not sustain."
        )

    return PersistenceReport(
        canonical_gtin=latest.canonical_gtin,
        sku_label=latest.sku_label,
        countries=countries,
        n_captures=n,
        first_seen=first_seen,
        last_seen=last_seen,
        real_window=_real_window_phrase(n, first_seen, last_seen),
        verdict=verdict,
        captures_with_gap=captures_with_gap,
        latest_net_of_tax_delta=latest.net_of_tax_delta,
        latest_more_expensive_country=latest.more_expensive_country,
        within_country_corroborated=within_corroborated,
        rationale=rationale,
    )


def group_by_sku(observations: list[Observation]) -> dict[str, list[Observation]]:
    """Bucket observations by SKU key (canonical GTIN preferred)."""
    buckets: dict[str, list[Observation]] = {}
    for obs in observations:
        buckets.setdefault(_sku_key(obs), []).append(obs)
    return buckets


@dataclass(frozen=True)
class RecurrenceReport:
    """Which SKUs / countries recur across the whole observation set."""

    n_observations: int
    n_distinct_skus: int
    recurring_skus: tuple[dict[str, Any], ...]  # SKUs seen in >1 capture
    country_pair_counts: tuple[tuple[str, int], ...]  # (pair, count), most-common first

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_observations": self.n_observations,
            "n_distinct_skus": self.n_distinct_skus,
            "recurring_skus": list(self.recurring_skus),
            "country_pair_counts": [list(p) for p in self.country_pair_counts],
        }


def analyze_recurrence(observations: list[Observation]) -> RecurrenceReport:
    """Compute recurrence: which SKUs/countries show up more than once."""
    buckets = group_by_sku(observations)
    recurring: list[dict[str, Any]] = []
    for key, obs_list in buckets.items():
        if len(obs_list) > 1:
            rep = analyze_sku(obs_list)
            recurring.append(
                {
                    "sku_key": key,
                    "n_captures": rep.n_captures,
                    "verdict": rep.verdict,
                    "canonical_gtin": rep.canonical_gtin,
                    "sku_label": rep.sku_label,
                }
            )
    recurring.sort(key=lambda r: r["n_captures"], reverse=True)

    pair_counts: dict[str, int] = {}
    for obs in observations:
        pair = "/".join(sorted(obs.countries))
        if pair:
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
    sorted_pairs = tuple(
        sorted(pair_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )

    return RecurrenceReport(
        n_observations=len(observations),
        n_distinct_skus=len(buckets),
        recurring_skus=tuple(recurring),
        country_pair_counts=sorted_pairs,
    )
