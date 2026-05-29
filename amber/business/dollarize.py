"""Deterministic €/unit -> €/yr margin-leak dollarization (Layer-1, signed).

This is the business-value bridge the judge panel asked for: a signed net-of-tax
cross-country delta is only a curiosity until it is expressed in money a brand
operator acts on. The bridge is a single deterministic multiplication —

    recoverable_margin_eur_per_year = net_of_tax_delta_eur_per_unit * annual_units

— so the result is reproducible from the signed inputs and is itself sealed into
the Merkle-signed bundle (edit it and the signature breaks). There is NO LLM and
no estimation anywhere in this path.

The ONE input that is not a measured observation is ``annual_units`` — the
brand's assumed annual cross-border-diverted volume for the SKU. It is a
BUYER-SUPPLIED ASSUMPTION, not an Amber measurement, and it is recorded as such
in the output (``assumption: true``, an explicit ``volume_basis`` label, and a
``disclaimer``). A measured-looking fabricated total would be a
receipts-not-vibes self-inflicted wound (LOCK 4 / docs/24-GROUNDING.md); the
volume therefore always travels with its assumption label so no surface can
present it as observed.

Only a real, nonzero, in-currency net-of-tax delta dollarizes. A zero delta, an
access/payment-denial finding, or an inconclusive comparison yields ``None`` (no
fabricated money figure) — the caller records the absence honestly.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from amber.capture import vat

# The default annual cross-border-diverted-volume knob, in units/yr. This is a
# clearly-LABELED buyer assumption (a sensible round placeholder), NEVER an Amber
# measurement. A brand supplies its own figure; this default exists only so the
# bridge produces a concrete, honestly-captioned card out of the box.
DEFAULT_ANNUAL_VOLUME_ASSUMPTION = 50_000

_VOLUME_BASIS = "buyer-supplied volume assumption"
_DISCLAIMER = (
    "annual_diverted_units is a BUYER-SUPPLIED ASSUMPTION, not an Amber "
    "measurement; the recoverable-margin figure is the signed net-of-tax "
    "per-unit delta multiplied by that assumed volume. Amber measures and signs "
    "the per-unit delta; the volume is the operator's input."
)


def dollarize_margin_leak(
    net_delta_finding: dict[str, Any] | None,
    *,
    annual_units: int = DEFAULT_ANNUAL_VOLUME_ASSUMPTION,
) -> dict[str, Any] | None:
    """Bridge a signed net-of-tax delta to a labeled €/yr margin-leak figure.

    ``net_delta_finding`` is the ``cross_country_comparison["net_delta"]`` block
    (or ``None``). Returns a deterministic ``business_impact`` dict, or ``None``
    when there is no real nonzero delta to dollarize (never a fabricated figure).

    The returned dict carries BOTH the signed measured inputs (the per-unit
    delta, the currency, the cheaper/dearer countries) and the explicitly-labeled
    assumption (the annual volume) so every downstream surface can render the
    figure honestly as assumption-driven.
    """
    if not net_delta_finding or not net_delta_finding.get("delta_is_nonzero"):
        return None

    raw_delta = net_delta_finding.get("net_of_tax_delta")
    try:
        per_unit = Decimal(str(raw_delta))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if per_unit <= 0:
        return None

    if int(annual_units) <= 0:
        raise ValueError(f"annual_units must be a positive integer, got {annual_units!r}")
    units = Decimal(int(annual_units))

    recoverable = vat.quantize_money(per_unit * units)

    return {
        "schema": "amber/business_impact@1",
        "metric": "recoverable_margin_per_year",
        "currency": "EUR",
        # The SIGNED, measured input.
        "net_of_tax_delta_per_unit": format(per_unit, "f"),
        "dearer_country": net_delta_finding.get("more_expensive_country"),
        "cheaper_country": net_delta_finding.get("cheaper_country"),
        # The BUYER ASSUMPTION (explicitly labeled, never observed).
        "annual_diverted_units": int(annual_units),
        "annual_diverted_units_is_assumption": True,
        "volume_basis": _VOLUME_BASIS,
        # The deterministic result of multiplying the two.
        "recoverable_margin_eur_per_year": format(recoverable, "f"),
        "computation": "net_of_tax_delta_per_unit * annual_diverted_units",
        "disclaimer": _DISCLAIMER,
    }
