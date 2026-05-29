"""Jurisdiction- and category-correct VAT/GST table + net-of-tax computation.

The honest price comparison is **net of tax**: two EU countries can charge the
same pre-tax price and still show different shelf prices purely because their
standard VAT rates differ (DE 19 %, BE 21 %). A naive "gross delta" reports that
tax artifact as if it were a discriminatory price gap. Amber subtracts the
*correct* statutory rate for the country + product category and reports BOTH the
gross and the net-of-tax figures, with the rate's SOURCE recorded inline so the
signed fact is auditable.

Every rate carries a ``source`` string (the statutory citation) and an
``as_of`` date. The table is data, committed to the repo, and recorded verbatim
into ``facts.json`` for each capture so a verifier sees exactly which rate was
applied and where it came from — no rate is an unsourced magic number.

Rates here are the **standard** and selected **reduced** EU VAT rates as
published in the European Commission "VAT rates applied in the Member States of
the European Union" (Taxation and Customs Union; rates effective for 2025). They
are deterministic table lookups, never inferred.

NOTE on scope: this table covers the Phase-1 hero pair (DE, BE) and a handful of
other EU members for the within-country control / discovery. A country/category
not in the table yields ``None`` from :func:`lookup_rate` and forces the floor to
record ``VAT_RATE_UNAVAILABLE`` rather than guessing — surfacing the gap is the
root solution; a fabricated default rate is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Category keys are deliberately coarse and explicit. "standard" is the default
# for general merchandise (electronics, toys, homeware, etc.). Reduced-rate
# categories (books, food, etc.) are listed where Phase-1 needs them; an unknown
# category falls through to None (never silently to "standard").
CATEGORY_STANDARD = "standard"
CATEGORY_BOOKS = "books"
CATEGORY_FOOD = "food"


@dataclass(frozen=True)
class VatRate:
    """A single statutory VAT rate with its provenance.

    ``rate`` is the fraction (e.g. ``Decimal("0.19")`` for 19 %). ``source`` is
    the human-auditable citation recorded into the signed fact. ``as_of`` is the
    effectivity date of the rate in the source.
    """

    country: str
    category: str
    rate: Decimal
    source: str
    as_of: str

    def as_fact(self) -> dict[str, str]:
        """Serialise for embedding in ``facts.json`` (strings, never floats).

        Decimals are emitted as canonical decimal strings so the signed bytes are
        reproducible and a verifier can re-derive net = gross / (1 + rate).
        """
        return {
            "country": self.country,
            "category": self.category,
            "rate": format(self.rate, "f"),
            "source": self.source,
            "as_of": self.as_of,
        }


# Source string shared by the standard-rate rows (EC published table, 2025).
_EC_SRC = (
    "European Commission, Taxation and Customs Union — 'VAT rates applied in "
    "the Member States of the European Union' (2025 edition)"
)

# The committed VAT table. Standard rates verified against the EC 2025 table.
# Reduced rates included only for categories Phase 1 may touch (books).
_TABLE: dict[tuple[str, str], VatRate] = {}


def _add(country: str, category: str, rate: str, source: str, as_of: str) -> None:
    _TABLE[(country.upper(), category)] = VatRate(
        country=country.upper(),
        category=category,
        rate=Decimal(rate),
        source=source,
        as_of=as_of,
    )


# --- Standard rates (general merchandise) --------------------------------- #
# Hero pair first (the Phase-1 DE/BE comparison hinges on these two).
_add("DE", CATEGORY_STANDARD, "0.19", _EC_SRC, "2025-01-01")  # Germany 19 %
_add("BE", CATEGORY_STANDARD, "0.21", _EC_SRC, "2025-01-01")  # Belgium 21 %
# Additional EU members for within-country-control candidates / discovery.
_add("FR", CATEGORY_STANDARD, "0.20", _EC_SRC, "2025-01-01")  # France 20 %
_add("NL", CATEGORY_STANDARD, "0.21", _EC_SRC, "2025-01-01")  # Netherlands 21 %
_add("IT", CATEGORY_STANDARD, "0.22", _EC_SRC, "2025-01-01")  # Italy 22 %
_add("ES", CATEGORY_STANDARD, "0.21", _EC_SRC, "2025-01-01")  # Spain 21 %
_add("AT", CATEGORY_STANDARD, "0.20", _EC_SRC, "2025-01-01")  # Austria 20 %
_add("PL", CATEGORY_STANDARD, "0.23", _EC_SRC, "2025-01-01")  # Poland 23 %
_add("IE", CATEGORY_STANDARD, "0.23", _EC_SRC, "2025-01-01")  # Ireland 23 %
_add("LU", CATEGORY_STANDARD, "0.17", _EC_SRC, "2025-01-01")  # Luxembourg 17 %

# --- Selected reduced rates (only categories Phase 1 may need) ------------ #
# Books: DE 7 %, BE 6 % (printed books). Recorded so a book SKU is comparable
# net-of-tax without forcing the standard rate.
_add("DE", CATEGORY_BOOKS, "0.07", _EC_SRC, "2025-01-01")
_add("BE", CATEGORY_BOOKS, "0.06", _EC_SRC, "2025-01-01")


def lookup_rate(country: str, category: str = CATEGORY_STANDARD) -> VatRate | None:
    """Return the :class:`VatRate` for a country + category, or ``None``.

    ``None`` means the table has no statutory rate for this pair; the caller must
    record ``VAT_RATE_UNAVAILABLE`` rather than guess. Never returns a default.
    """
    return _TABLE.get((country.upper(), category))


def known_countries() -> set[str]:
    """All ISO-2 country codes present in the table (any category)."""
    return {country for (country, _cat) in _TABLE}


def net_of_tax(gross: Decimal, rate: Decimal) -> Decimal:
    """Compute the VAT-exclusive (net) amount from a gross amount + VAT fraction.

    ``net = gross / (1 + rate)`` rounded HALF_UP to 2 decimal places (currency).
    Both inputs are :class:`~decimal.Decimal` so there is no binary-float drift in
    the signed figure. Raises ``ValueError`` on a negative/invalid input rather
    than silently producing a wrong number.
    """
    if gross < 0:
        raise ValueError(f"gross amount must be non-negative, got {gross}")
    if rate < 0:
        raise ValueError(f"VAT rate must be non-negative, got {rate}")
    try:
        net = gross / (Decimal(1) + rate)
    except (InvalidOperation, ZeroDivisionError) as exc:  # 1+rate is never 0 for rate>=0
        raise ValueError(f"cannot compute net-of-tax for gross={gross} rate={rate}") from exc
    return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantize_money(amount: Decimal) -> Decimal:
    """Round a monetary :class:`~decimal.Decimal` to 2 dp HALF_UP."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
