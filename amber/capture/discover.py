"""Hero-SKU discovery — find a DE/BE SKU that genuinely fires.

Given a list of CANDIDATE product URLs (the operator's OWN catalogue — the demo
is a brand monitoring its own SKUs), capture each across Germany + Belgium with
the within-country control, run the deterministic floor, and SCORE each candidate
by the strength of a REAL finding:

  * a non-zero net-of-tax cross-country price delta on a GTIN-matched SKU whose
    intra-country exits agree, OR
  * a real access/payment denial (one country GEO_BLOCKED, another PURCHASABLE),

while DISQUALIFYING anything where identity is unverified, the state is
INCONCLUSIVE, or a soft-block contaminated the measurement.

The scorer is deterministic and honest: if NOTHING fires across all candidates,
it says so (``no_finding=True``) rather than picking a least-bad option or
inventing a delta. Surfacing "nothing fired on these SKUs — pick different ones"
is the correct, defensible outcome (a data-selection problem, not a result to
fake).

Like the rest of Component 2 this needs Bright Data credentials to run live; with
no creds it reports the pending live step. The scoring/ranking logic itself is
unit-tested offline against constructed floor outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from amber.capture import brightdata, credentials, floor, identity, state, vat
from amber.capture.record import CaptureRecord


@dataclass
class Candidate:
    """A scored discovery candidate for one product URL."""

    url: str
    sku_label: str | None
    facts: dict
    score: float
    finding_kind: str  # NET_OF_TAX_PRICE_DELTA / ACCESS_OR_PAYMENT_DENIAL / NONE
    disqualified: bool
    reasons: list[str] = field(default_factory=list)

    def evidence(self) -> dict:
        """A compact, secret-free evidence summary for the report."""
        comp = self.facts.get("cross_country_comparison", {})
        wcc = self.facts.get("within_country_control", {})
        return {
            "url": self.url,
            "sku_label": self.sku_label,
            "score": self.score,
            "finding_kind": self.finding_kind,
            "disqualified": self.disqualified,
            "reasons": list(self.reasons),
            "sku_identity_confidence": self.facts.get("sku_identity", {}).get("confidence"),
            "primary_finding": comp.get("primary_finding"),
            "net_delta": comp.get("net_delta"),
            "access_denial": comp.get("access_denial"),
            "within_country_all_agree": wcc.get("all_intra_country_agree"),
            "per_country_states": comp.get("per_country_states"),
        }


def score_candidate(url: str, facts: dict, sku_label: str | None = None) -> Candidate:
    """Deterministically score a candidate from its floor ``facts``.

    Scoring (higher = stronger hero):
      * GTIN_MATCH required for a price-delta finding; absent -> disqualified for
        a delta (a denial can still score, since identity matters less when the
        finding is "this country can't buy it at all").
      * A real access/payment denial scores highest (100 + ...).
      * A non-zero net-of-tax delta scores by magnitude, but ONLY if within-
        country exits AGREE (so the delta isn't exit noise) and no country is
        INCONCLUSIVE from a soft-block.
      * Anything INCONCLUSIVE / soft-blocked / no-finding -> disqualified, score 0.
    """
    reasons: list[str] = []
    comp = facts.get("cross_country_comparison", {})
    wcc = facts.get("within_country_control", {})
    id_conf = facts.get("sku_identity", {}).get("confidence")
    primary = comp.get("primary_finding")

    # Any soft-block-driven INCONCLUSIVE contaminates the measurement.
    per_states = comp.get("per_country_states", {})
    inconclusive_countries = [c for c, sts in per_states.items() if state.INCONCLUSIVE in sts]
    soft_blocked = any(
        cap.get("state", {}).get("soft_block", {}).get("is_soft_blocked")
        for cap in facts.get("per_capture", [])
    )

    # Access / payment denial — the strongest hero.
    if primary == "ACCESS_OR_PAYMENT_DENIAL" and comp.get("access_denial"):
        reasons.append("real access/payment denial: one country GEO_BLOCKED, another PURCHASABLE")
        return Candidate(
            url=url,
            sku_label=sku_label,
            facts=facts,
            score=100.0,
            finding_kind="ACCESS_OR_PAYMENT_DENIAL",
            disqualified=False,
            reasons=reasons,
        )

    # Net-of-tax price delta — requires identity + intra-country agreement + clean.
    if primary == "NET_OF_TAX_PRICE_DELTA" and comp.get("net_delta"):
        delta_str = comp["net_delta"].get("net_of_tax_delta", "0")
        delta = abs(Decimal(delta_str))
        ok = True
        if id_conf != identity.GTIN_MATCH:
            ok = False
            reasons.append(f"identity not GTIN_MATCH (got {id_conf}) — cannot claim same SKU")
        if not wcc.get("all_intra_country_agree"):
            ok = False
            reasons.append(
                "within-country exits DISAGREE — delta may be exit noise, not a real gap"
            )
        if soft_blocked:
            ok = False
            reasons.append("a soft-block contaminated at least one capture")
        if inconclusive_countries:
            ok = False
            reasons.append(f"INCONCLUSIVE country/countries present: {inconclusive_countries}")
        if ok and delta > 0:
            reasons.append(
                f"clean net-of-tax delta of {delta} on a GTIN-matched, "
                "intra-country-agreeing SKU"
            )
            return Candidate(
                url=url,
                sku_label=sku_label,
                facts=facts,
                score=float(delta),
                finding_kind="NET_OF_TAX_PRICE_DELTA",
                disqualified=False,
                reasons=reasons,
            )
        return Candidate(
            url=url,
            sku_label=sku_label,
            facts=facts,
            score=0.0,
            finding_kind="NONE",
            disqualified=True,
            reasons=reasons or ["delta present but disqualified"],
        )

    # No finding.
    if primary == "NO_NET_DELTA":
        reasons.append(
            "prices AGREE net-of-tax — a legitimate non-finding / control (no hero here)"
        )
    else:
        reasons.append(f"no real finding (primary={primary}); not a hero candidate")
    if soft_blocked:
        reasons.append("soft-block present")
    return Candidate(
        url=url, sku_label=sku_label, facts=facts, score=0.0,
        finding_kind="NONE", disqualified=True, reasons=reasons,
    )


@dataclass
class DiscoveryResult:
    """Ranked candidates + the chosen hero (or an honest no-finding)."""

    ran_live: bool
    candidates: list[Candidate]
    hero: Candidate | None
    no_finding: bool
    message: str = ""

    def as_report(self) -> dict:
        return {
            "ran_live": self.ran_live,
            "no_finding": self.no_finding,
            "hero": self.hero.evidence() if self.hero else None,
            "candidates": [c.evidence() for c in self.candidates],
            "message": self.message,
        }


def rank(candidates: list[Candidate]) -> DiscoveryResult:
    """Rank scored candidates; pick the strongest qualified one as the hero.

    Denials outrank deltas (finding_kind ordering), then by score. If no
    candidate qualifies, ``no_finding`` is True and ``hero`` is None — the honest
    outcome, never a forced pick.
    """
    kind_rank = {"ACCESS_OR_PAYMENT_DENIAL": 2, "NET_OF_TAX_PRICE_DELTA": 1, "NONE": 0}
    ordered = sorted(
        candidates,
        key=lambda c: (0 if c.disqualified else 1, kind_rank[c.finding_kind], c.score),
        reverse=True,
    )
    qualified = [c for c in ordered if not c.disqualified]
    hero = qualified[0] if qualified else None
    return DiscoveryResult(
        ran_live=False,
        candidates=ordered,
        hero=hero,
        no_finding=hero is None,
        message=(
            f"{len(qualified)} of {len(candidates)} candidate(s) fired a real finding"
            if qualified
            else "NO candidate fired a real finding — pick different SKUs "
            "(a data-selection problem, surfaced honestly, not faked)"
        ),
    )


def discover(
    candidate_urls: list[tuple[str, str | None]],
    countries: list[str],
    sessions_per_country: int,
    *,
    category: str = vat.CATEGORY_STANDARD,
    timeout: int = brightdata.DEFAULT_TIMEOUT,
) -> DiscoveryResult:
    """Live discovery across candidate URLs. Reports pending if no BD creds.

    ``candidate_urls`` is a list of ``(url, sku_label)``. Returns a
    :class:`DiscoveryResult`. With no credentials, ``ran_live`` is False and the
    message states the pending live step — nothing is fabricated.
    """
    creds = credentials.load()
    if creds is None:
        return DiscoveryResult(
            ran_live=False,
            candidates=[],
            hero=None,
            no_finding=True,
            message=(
                "Bright Data credentials ABSENT — hero-SKU discovery is the live "
                "step pending creds. Provide candidate OWN-brand SKU URLs and set "
                "BD creds to run; the scoring/ranking logic is unit-tested offline."
            ),
        )

    scored: list[Candidate] = []
    for url, label in candidate_urls:
        records: list[CaptureRecord] = brightdata.same_second_batch(
            creds, url, countries, sessions_per_country, timeout=timeout
        )
        facts = floor.build_facts(url, records, category=category, sku_label=label)
        scored.append(score_candidate(url, facts, sku_label=label))

    result = rank(scored)
    result.ran_live = True
    return result
