"""The legal taxonomy for the Layer-2 jury — grounded in Reg (EU) 2018/302.

This is a **Phase-2** module. Its output is **Layer 2 = labeled INTERPRETATION,
UNSIGNED**. Per LOCK 4 the AI legal label is NEVER written into the signed
Layer-1 packet; an LLM never computes a fact or number into the signed bundle.
The jury reads the *already-signed* deterministic facts and emits a separate
advisory.

The labels below are the full classification space. Each carries a short,
verbatim-grounded criterion from Reg (EU) 2018/302 (the EU Geo-Blocking
Regulation) so the three models classify against the SAME rule text, not their
own paraphrases. Reg 2018/302 is about ACCESS, not price parity: it PERMITS
different net prices per member state but PROHIBITS blocking / re-routing /
refusing a customer in one member state from accessing and buying at the offer
available in another, and prohibits discriminatory payment refusal — unless an
objective justification applies (see docs/24-GROUNDING.md, LOCK 9).
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical label tokens. These are the ONLY values the consensus may emit
# (plus the routing token ROUTE_TO_HUMAN, which is a consensus *outcome*, not a
# model label).
PROHIBITED_GEO_BLOCKING = "PROHIBITED_GEO_BLOCKING"
PERMITTED_OBJECTIVE_JUSTIFICATION = "PERMITTED_OBJECTIVE_JUSTIFICATION"
DMA_SELF_PREFERENCING = "DMA_SELF_PREFERENCING"
DYNAMIC_PRICING = "DYNAMIC_PRICING"
TAX_DUTY_ARTIFACT = "TAX_DUTY_ARTIFACT"
GRAY_MARKET_CAPACITY = "GRAY_MARKET_CAPACITY"
INSUFFICIENT_INFO = "INSUFFICIENT_INFO"

# Emitted by the consensus (never by a single model) when the jury does not
# reach a majority — the disagreement is routed to a human, never auto-resolved.
ROUTE_TO_HUMAN = "ROUTE_TO_HUMAN"


@dataclass(frozen=True)
class Label:
    """One taxonomy label + the Reg 2018/302 criterion that defines it."""

    token: str
    criterion: str


# The canonical, ordered taxonomy. The criteria are the grounding text injected
# verbatim into every model's system prompt so the jury reasons against the
# actual rule, not a model's recollection of it.
TAXONOMY: tuple[Label, ...] = (
    Label(
        PROHIBITED_GEO_BLOCKING,
        "Arts 3-5: a customer in one member state is blocked, automatically "
        "re-routed, or refused access/checkout/delivery that another member "
        "state completes, on the basis of nationality/residence/place of "
        "establishment, with NO objective justification. (Reg 2018/302 targets "
        "ACCESS, not price parity.)",
    ),
    Label(
        PERMITTED_OBJECTIVE_JUSTIFICATION,
        "An access or condition difference exists BUT a lawful objective "
        "justification applies (a legal obligation in the customer's member "
        "state, or compliance with a Union/national law) — Art 3(3)/recitals. "
        "The differential is permitted, not prohibited.",
    ),
    Label(
        DMA_SELF_PREFERENCING,
        "The pattern is gatekeeper self-preferencing under the Digital Markets "
        "Act (e.g., a designated gatekeeper ranking/conditioning its own offer "
        "above third parties) rather than territorial geo-blocking under "
        "2018/302. Use only when the facts indicate a gatekeeper, not pure geo.",
    ),
    Label(
        DYNAMIC_PRICING,
        "The price difference is attributable to time/demand-based dynamic "
        "pricing rather than the customer's geography. Reg 2018/302 does not "
        "prohibit dynamic pricing; geography is not the discriminating variable.",
    ),
    Label(
        TAX_DUTY_ARTIFACT,
        "The ENTIRE observed gross difference is explained by VAT/duty: the "
        "net-of-tax prices agree (net delta ~= 0). No prohibited differential "
        "remains once tax is removed. A lawful tax artifact, not geo-blocking.",
    ),
    Label(
        GRAY_MARKET_CAPACITY,
        "The difference is explained by gray-market / capacity / authorized-"
        "channel scope (e.g., the SKU is genuinely a different authorized "
        "offer per market), not by refusing a member state access to the same "
        "offer.",
    ),
    Label(
        INSUFFICIENT_INFO,
        "The signed Layer-1 facts do not support any confident classification "
        "(e.g., a soft-block forced INCONCLUSIVE, only one country resolved, or "
        "no causally-independent access-denial signal). Decline rather than "
        "guess.",
    ),
)

# Fast lookups derived from the canonical tuple.
LABEL_TOKENS: tuple[str, ...] = tuple(label.token for label in TAXONOMY)
LABELS_BY_TOKEN: dict[str, Label] = {label.token: label for label in TAXONOMY}

VALID_TOKENS: frozenset[str] = frozenset(LABEL_TOKENS)


def is_valid_label(token: str) -> bool:
    """True iff ``token`` is one of the canonical model-emittable labels."""
    return token in VALID_TOKENS


def taxonomy_prompt_block() -> str:
    """Render the taxonomy + Reg 2018/302 criteria as a prompt-ready block.

    Injected verbatim into every juror's system prompt so all three models
    classify against identical rule text.
    """
    lines = []
    for label in TAXONOMY:
        lines.append(f"- {label.token}: {label.criterion}")
    return "\n".join(lines)
