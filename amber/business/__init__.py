"""The deterministic dollarization bridge (Layer-1, SIGNED).

Turns the signed net-of-tax €/unit cross-country delta into a CRO-legible
€/yr margin-leak figure — deterministically (NO LLM), so the result is itself a
Layer-1 fact that gets sealed into the Merkle-signed bundle.

The arithmetic is pure (``delta_eur_per_unit × annual_units``); the only input
that is not a measured observation is the annual diverted-volume knob, which is a
BUYER-SUPPLIED ASSUMPTION and is recorded as such (``assumption: true``,
``source: "buyer-supplied volume assumption"``) — never presented as observed.
"""

from amber.business.dollarize import (
    DEFAULT_ANNUAL_VOLUME_ASSUMPTION,
    dollarize_margin_leak,
)

__all__ = ["DEFAULT_ANNUAL_VOLUME_ASSUMPTION", "dollarize_margin_leak"]
