"""Per-geo factual-state classification with the GEO_BLOCKED >=2-signal floor.

Given one capture (its status, headers, extracted product fields, soft-block
verdict, and geo-attribution), classify the deterministic factual state:

    PURCHASABLE     a product page with a price and an in-stock / no-explicit-
                    block signal — the customer in this geo can buy it.
    OUT_OF_STOCK    a product page that exists but is explicitly out of stock.
    NOT_SOLD_HERE   the catalogue explicitly does not carry the item for this
                    geo (a distinct, non-blocking "we don't sell this here").
    GEO_BLOCKED     access/purchase is refused for a geo reason — REQUIRES >=2
                    CAUSALLY-INDEPENDENT signals (honesty rule #8).
    PRICE_GATED     the price is hidden behind login / "add to cart to see price"
                    (a real condition-difference signal, not a block).
    INCONCLUSIVE    we cannot make a defensible call — INCLUDING any time a
                    soft-block / anti-bot gate fired (forced, regardless of any
                    geo-reason text).

The non-negotiable rules implemented here:
  * A soft-block forces INCONCLUSIVE. Geo-reason text on a challenge page is
    discarded entirely (it cannot contribute a GEO_BLOCKED signal).
  * GEO_BLOCKED needs >=2 signals AND those signals must be causally independent
    (drawn from different signal CLASSES). One signal -> never GEO_BLOCKED.
  * INCONCLUSIVE never auto-promotes to anything stronger.

A signal "class" groups signals by their causal origin so two facets of the same
cause cannot masquerade as two independent confirmations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from amber.capture import softblock
from amber.capture.extract import Extracted

# Factual-state tokens (the closed set from the spec / glossary).
PURCHASABLE = "PURCHASABLE"
OUT_OF_STOCK = "OUT_OF_STOCK"
NOT_SOLD_HERE = "NOT_SOLD_HERE"
GEO_BLOCKED = "GEO_BLOCKED"
PRICE_GATED = "PRICE_GATED"
INCONCLUSIVE = "INCONCLUSIVE"

# Causally-independent signal CLASSES for a GEO_BLOCKED determination. Two
# signals only count as independent if they come from DIFFERENT classes.
SIGNAL_CLASS_STATUS = "http_status"  # e.g. 451 Unavailable For Legal Reasons
SIGNAL_CLASS_DOM_REASON = "dom_geo_reason"  # explicit on-page geo-reason text
SIGNAL_CLASS_REDIRECT = "geo_redirect"  # a Location redirect to a geo gate
SIGNAL_CLASS_CHECKOUT = "checkout_rejection"  # payment/checkout refused for geo
SIGNAL_CLASS_CATALOG = "catalog_absence"  # item absent from the geo catalogue

# Causal GROUPS: two detector classes in the same group are facets of ONE
# underlying cause and together count as a SINGLE causal signal, never two. The
# storefront served the refusal in its response body — whether the matched text
# reads as a geo-reason sentence or a payment/shipping rejection, it is one
# storefront-served geo-refusal, not two independent confirmations. A genuine
# second confirmation MUST come from a different layer (transport/status 451 or a
# geo-redirect Location header), which is why those classes are in their own
# groups. Any class not listed is its own group (group == the class name).
_CAUSAL_GROUPS: dict[str, str] = {
    SIGNAL_CLASS_DOM_REASON: "storefront_served_geo_refusal",
    SIGNAL_CLASS_CHECKOUT: "storefront_served_geo_refusal",
}


def _causal_group(signal_class: str) -> str:
    """The underlying-cause group for a detector class (defaults to the class)."""
    return _CAUSAL_GROUPS.get(signal_class, signal_class)


# HTTP 451 = Unavailable For Legal Reasons — a strong, distinct geo-block status.
_GEO_BLOCK_STATUS = 451


@dataclass
class GeoBlockSignal:
    """One candidate GEO_BLOCKED signal + its causal class."""

    signal_class: str
    detail: str

    def as_fact(self) -> dict:
        return {"signal_class": self.signal_class, "detail": self.detail}


@dataclass
class StateResult:
    """The classified factual state of one capture + its rationale.

    ``state`` is the verdict. ``geo_block_signals`` lists the (>=2, independent)
    signals that justified GEO_BLOCKED (empty for other states). ``rationale``
    explains the determination for the signed fact.
    """

    state: str
    rationale: str
    geo_block_signals: list[GeoBlockSignal] = field(default_factory=list)
    soft_block: softblock.SoftBlockResult | None = None

    def as_fact(self) -> dict:
        return {
            "state": self.state,
            "rationale": self.rationale,
            "geo_block_signals": [s.as_fact() for s in self.geo_block_signals],
            "soft_block": self.soft_block.as_fact() if self.soft_block else None,
        }


def _collect_geo_block_signals(
    http_status: int,
    headers: dict[str, str],
    body: bytes,
) -> list[GeoBlockSignal]:
    """Gather candidate GEO_BLOCKED signals, each tagged with its causal class.

    Only called when NO soft-block is present (the caller enforces that). Signals
    are deduplicated by underlying CAUSE (their causal GROUP, see
    :data:`_CAUSAL_GROUPS`), not by which lexical detector fired. So a single
    storefront response that trips both the on-page geo-reason regex AND a
    checkout/payment-rejection marker yields ONE "storefront-served geo-refusal"
    signal — not two — because both are facets of the same cause. A genuine
    second independent signal must come from a different layer (HTTP 451, or a
    geo-redirect Location), which lives in its own causal group.
    """
    signals: list[GeoBlockSignal] = []
    seen_groups: set[str] = set()

    def add(cls: str, detail: str) -> None:
        group = _causal_group(cls)
        if group not in seen_groups:
            signals.append(GeoBlockSignal(signal_class=cls, detail=detail))
            seen_groups.add(group)

    headers_lc = {k.lower(): str(v) for k, v in headers.items()}

    # Class: HTTP status (451 Unavailable For Legal Reasons).
    if http_status == _GEO_BLOCK_STATUS:
        add(SIGNAL_CLASS_STATUS, "http 451 Unavailable For Legal Reasons")

    # Class: geo-redirect (a Location to a region-gate / different-country store).
    loc = headers_lc.get("location", "")
    if loc and any(tok in loc.lower() for tok in ("geo", "region", "country", "blocked")):
        add(SIGNAL_CLASS_REDIRECT, f"geo-redirect Location: {loc}")

    # Class: explicit on-page geo-reason text.
    reason = softblock.detect_geo_reason_text(body)
    if reason:
        add(SIGNAL_CLASS_DOM_REASON, f"on-page geo-reason: {reason!r}")

    # Class: checkout/payment rejection (an explicit machine marker in the body).
    # These markers are deliberately payment/shipping-specific phrases that the
    # geo-reason regex does NOT match, so they cannot fire off the same sentence a
    # dom_geo_reason already fired off. (Phrases like "cannot ship to your
    # country" or "unavailable in your region" are geo-reason text and are
    # detected as dom_geo_reason — NOT here — and the two are in any case collapsed
    # to one causal group, so a single storefront response is one signal.)
    text_lc = body.decode("utf-8", errors="replace").lower()
    if any(
        marker in text_lc
        for marker in (
            "payment method declined for your billing address",
            "we are unable to process payment from your card's country",
            "this card cannot be used for orders shipped to",
            "delivery address rejected at checkout",
        )
    ):
        add(SIGNAL_CLASS_CHECKOUT, "explicit checkout/payment geo-rejection")

    return signals


def classify(
    http_status: int,
    headers: dict[str, str],
    body: bytes,
    extracted: Extracted,
    soft_block: softblock.SoftBlockResult,
) -> StateResult:
    """Classify the deterministic factual state of one capture.

    Order of precedence (root rules first):
      1. Soft-block detected -> INCONCLUSIVE (forced; geo-reason text discarded).
      2. >=2 causally-independent GEO_BLOCKED signals -> GEO_BLOCKED.
      3. Exactly 1 GEO_BLOCKED signal -> INCONCLUSIVE (the >=2 floor; never
         auto-promoted), with the lone signal recorded for the re-test step.
      4. A parsed price + in-stock-ish availability -> PURCHASABLE.
      5. A product node but explicit out-of-stock -> OUT_OF_STOCK.
      6. Price gated (login/hidden price marker) -> PRICE_GATED.
      7. Explicit catalogue absence (non-blocking "not sold here") -> NOT_SOLD_HERE.
      8. Anything else -> INCONCLUSIVE.
    """
    # 1. Soft-block forces INCONCLUSIVE. This is the credibility gate.
    if soft_block.is_soft_blocked:
        return StateResult(
            state=INCONCLUSIVE,
            rationale=(
                "soft-block / anti-bot gate detected -> INCONCLUSIVE (forced); "
                "any geo-reason text is disregarded; re-test from a clean "
                "in-country IP before any GEO_BLOCKED call. signals="
                f"{soft_block.signals}"
            ),
            soft_block=soft_block,
        )

    # 2 & 3. GEO_BLOCKED needs >=2 causally-independent signals.
    geo_signals = _collect_geo_block_signals(http_status, headers, body)
    if len(geo_signals) >= 2:
        return StateResult(
            state=GEO_BLOCKED,
            rationale=(
                f"{len(geo_signals)} causally-independent geo-block signals "
                f"(classes: {[s.signal_class for s in geo_signals]})"
            ),
            geo_block_signals=geo_signals,
            soft_block=soft_block,
        )
    if len(geo_signals) == 1:
        return StateResult(
            state=INCONCLUSIVE,
            rationale=(
                "exactly 1 geo-block signal (class "
                f"{geo_signals[0].signal_class!r}) — below the >=2 "
                "causally-independent floor; INCONCLUSIVE, do NOT auto-promote. "
                "Re-test from a clean in-country IP to seek a second independent "
                "signal."
            ),
            geo_block_signals=geo_signals,
            soft_block=soft_block,
        )

    # 4-7. No geo-block signals: classify normal availability states.
    text_lc = body.decode("utf-8", errors="replace").lower()

    # PRICE_GATED: an explicit "log in / add to cart to see price" marker AND no
    # price extracted. (If a price WAS extracted, it isn't gated.)
    price_gate_markers = (
        "log in to see price",
        "login to see price",
        "sign in for price",
        "add to cart to see price",
        "price available after login",
        "price hidden",
    )
    if extracted.price is None and any(m in text_lc for m in price_gate_markers):
        return StateResult(
            state=PRICE_GATED,
            rationale="price hidden behind login / add-to-cart gate (no price served)",
            soft_block=soft_block,
        )

    if extracted.availability == OUT_OF_STOCK:
        return StateResult(
            state=OUT_OF_STOCK,
            rationale="product page served with explicit out-of-stock availability",
            soft_block=soft_block,
        )

    # NOT_SOLD_HERE: explicit non-blocking catalogue absence (distinct from a
    # geo-block — e.g. a 200 OK page that says the item isn't part of this
    # country's catalogue, with NO access refusal).
    not_sold_markers = (
        "not part of our assortment in",
        "not in our catalogue for",
        "this product is not carried in",
        "not offered in this store",
    )
    if extracted.price is None and any(m in text_lc for m in not_sold_markers):
        return StateResult(
            state=NOT_SOLD_HERE,
            rationale="explicit non-blocking catalogue absence for this geo",
            soft_block=soft_block,
        )

    # PURCHASABLE: a price was served and availability isn't out-of-stock.
    if extracted.price is not None and extracted.availability != OUT_OF_STOCK:
        avail = extracted.availability or "unspecified"
        return StateResult(
            state=PURCHASABLE,
            rationale=f"price served ({extracted.price} {extracted.currency}); "
            f"availability={avail}",
            soft_block=soft_block,
        )

    # 8. Default: not enough to make any defensible call.
    return StateResult(
        state=INCONCLUSIVE,
        rationale=(
            "no price, no explicit availability/geo signal could be extracted "
            f"deterministically (extract.source={extracted.source}, "
            f"http_status={http_status}) — INCONCLUSIVE rather than a guess"
        ),
        soft_block=soft_block,
    )
