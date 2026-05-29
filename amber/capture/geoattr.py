"""Two-source signed geo-attribution.

The crypto in Component 1 authenticates the *file* — it proves the bytes weren't
altered. It does NOT, by itself, prove the capture came from the country the
manifest claims. A litigator's first question is "how do you know this body was
served to a German visitor?" Amber answers with **two independent sources** that
must agree before a geo claim is asserted:

  Source 1 — the network exit (where the request came FROM):
      the Bright Data residential exit IP, attributed to a country by its RIR
      (Regional Internet Registry) registration. We classify the exit IP to a
      country via:
        (a) the registry country reported by Bright Data for the session
            (recorded as ``proxy_reported_country``), and
        (b) a registry lookup of the exit IP — an offline RIR/whois country.

  Source 2 — the response geo-signals (what the SERVER served, geo-wise):
      the response's geo-revealing headers and observable currency:
      ``Content-Language`` / ``Accept-Language`` echo, ``Content-Language``,
      currency in the body/headers, and any geo-redirect ``Location``.

The :func:`attribute` function records BOTH sources verbatim and computes an
``agreement`` verdict (``CONFIRMED`` when the exit-IP country and at least one
response geo-signal corroborate the requested country; ``EXIT_ONLY`` when only
the network side is known; ``CONFLICT`` when they actively disagree). The whole
record is a deterministic dict embedded in the signed facts — so the geo claim
travels with its evidence, not just an assertion.

Offline by default: the RIR country comes from a bundled IANA delegated-extent
table snapshot (no network needed, so tests + the golden run are reproducible).
A live whois enrichment is available but never required and never the sole source.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from pathlib import Path

# Where the offline RIR delegation snapshot lives (CIDR -> ISO-2 country).
# Bundled so attribution is reproducible offline; the harness can refresh it from
# the public IANA/RIR delegated-extended files but never depends on the network
# at verify/replay time.
_RIR_SNAPSHOT = Path(__file__).resolve().parent / "data" / "rir_country_blocks.tsv"


@dataclass(frozen=True)
class _CidrCountry:
    network: ipaddress.IPv4Network | ipaddress.IPv6Network
    country: str
    source: str  # e.g. "ripencc" / "arin" — the registry that delegated it


def _load_rir_snapshot(path: Path) -> list[_CidrCountry]:
    """Load the bundled CIDR->country table. Empty list if the snapshot is absent.

    Each non-comment line: ``<cidr>\\t<ISO2>\\t<registry>``. Malformed lines are
    a data error — they are skipped but counted by the caller via the parse, not
    silently corrupting the table. We keep parsing strict-ish: a bad CIDR raises,
    which surfaces a corrupt snapshot rather than masking it.
    """
    if not path.exists():
        return []
    rows: list[_CidrCountry] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"malformed RIR snapshot line (expected 3 cols): {line!r}")
        cidr, cc, registry = parts
        net = ipaddress.ip_network(cidr, strict=False)
        rows.append(_CidrCountry(network=net, country=cc.upper(), source=registry))
    return rows


# Loaded once at import. A list ordered most-specific-first improves longest-
# prefix matching; we sort by prefix length descending so a more specific block
# wins over an enclosing one.
_RIR_TABLE: list[_CidrCountry] = sorted(
    _load_rir_snapshot(_RIR_SNAPSHOT),
    key=lambda r: r.network.prefixlen,
    reverse=True,
)


def rir_country_for_ip(ip: str) -> tuple[str | None, str | None]:
    """Look up an IP's country in the bundled RIR snapshot (longest-prefix).

    Returns ``(ISO2_country, registry)`` or ``(None, None)`` if the IP is not in
    the snapshot. Deterministic + offline. Never raises on a normal lookup; an
    invalid IP string returns ``(None, None)`` (the caller already validated, but
    we are defensive against a tamperer-supplied exit_ip).
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None, None
    for row in _RIR_TABLE:
        if addr.version == row.network.version and addr in row.network:
            return row.country, row.source
    return None, None


# Response geo-signal header names we record (lower-cased).
GEO_SIGNAL_HEADERS = (
    "content-language",
    "content-currency",
    "x-currency",
    "location",  # a geo-redirect Location is a strong server-side geo signal
    "set-cookie",  # country/locale cookies often appear here
    "vary",
)

# ISO-4217 currency -> the set of EU countries that use it (for the currency
# corroboration signal). Eurozone members all use EUR, so EUR alone does NOT pin
# a single country — it only confirms "an EU country", which is still a weak
# corroborating signal but never a *unique* attribution. Non-euro EU currencies
# (e.g. PLN, SEK, DKK) DO pin a country.
_CURRENCY_TO_COUNTRIES: dict[str, set[str]] = {
    "PLN": {"PL"},
    "SEK": {"SE"},
    "DKK": {"DK"},
    "CZK": {"CZ"},
    "HUF": {"HU"},
    "RON": {"RO"},
    "BGN": {"BG"},
    # EUR intentionally omitted: it does not pin a single country.
}

# Eurozone members (subset relevant to Phase-1 candidates). Used only to record
# "EUR is consistent with this EU country" — never to assert a unique country.
_EUROZONE = {"DE", "BE", "FR", "NL", "IT", "ES", "AT", "IE", "LU", "PT", "FI", "GR"}


@dataclass
class GeoAttribution:
    """The two-source attribution record for one capture.

    Embedded verbatim into the per-geo fact. ``agreement`` is the verdict:
      - ``CONFIRMED``  exit-IP country == requested AND a response signal agrees
      - ``EXIT_ONLY``  exit-IP country == requested, no corroborating response signal
      - ``CONFLICT``   exit-IP country or a response signal disagrees with requested
      - ``UNATTRIBUTED`` exit-IP country unknown (snapshot miss) and no signal
    """

    requested_country: str
    exit_ip: str
    proxy_reported_country: str | None
    rir_country: str | None
    rir_registry: str | None
    response_geo_signals: dict[str, str] = field(default_factory=dict)
    currency_observed: str | None = None
    currency_consistent_countries: list[str] = field(default_factory=list)
    agreement: str = "UNATTRIBUTED"
    notes: list[str] = field(default_factory=list)

    def as_fact(self) -> dict:
        return {
            "requested_country": self.requested_country,
            "source_1_network_exit": {
                "exit_ip": self.exit_ip,
                "proxy_reported_country": self.proxy_reported_country,
                "rir_country": self.rir_country,
                "rir_registry": self.rir_registry,
            },
            "source_2_response_geo_signals": {
                "headers": dict(self.response_geo_signals),
                "currency_observed": self.currency_observed,
                "currency_consistent_countries": list(self.currency_consistent_countries),
            },
            "agreement": self.agreement,
            "notes": list(self.notes),
        }


def _extract_geo_signal_headers(headers: dict[str, str]) -> dict[str, str]:
    """Pull the geo-revealing headers (lower-cased keys) we record as Source 2."""
    lower = {k.lower(): v for k, v in headers.items()}
    return {h: lower[h] for h in GEO_SIGNAL_HEADERS if h in lower}


def _currency_consistency(currency: str | None) -> list[str]:
    """Countries consistent with an observed currency code.

    A non-euro currency pins a single country. EUR returns the eurozone set
    (consistency, not a unique pin). Unknown currency -> empty list.
    """
    if not currency:
        return []
    cur = currency.upper()
    if cur == "EUR":
        return sorted(_EUROZONE)
    return sorted(_CURRENCY_TO_COUNTRIES.get(cur, set()))


def attribute(
    requested_country: str,
    exit_ip: str,
    response_headers: dict[str, str],
    *,
    proxy_reported_country: str | None = None,
    currency_observed: str | None = None,
) -> GeoAttribution:
    """Build the two-source geo-attribution record + agreement verdict.

    Deterministic. ``requested_country`` is what we asked Bright Data to exit
    from; the verdict says whether the two independent sources back that claim.
    """
    req = requested_country.upper()
    rir_cc, rir_reg = rir_country_for_ip(exit_ip)
    geo_headers = _extract_geo_signal_headers(response_headers)
    cur_countries = _currency_consistency(currency_observed)

    notes: list[str] = []

    # Source 1 verdict: does the network exit place us in the requested country?
    exit_country = rir_cc or (proxy_reported_country.upper() if proxy_reported_country else None)
    exit_agrees = exit_country == req if exit_country else None
    if rir_cc and proxy_reported_country and rir_cc != proxy_reported_country.upper():
        notes.append(
            f"exit-IP RIR country {rir_cc} differs from proxy-reported "
            f"{proxy_reported_country.upper()}"
        )

    # Source 2 verdict: does any response geo-signal corroborate the requested
    # country? content-language prefix or a country-pinning currency.
    response_agrees: bool | None = None
    cl = geo_headers.get("content-language", "")
    if cl:
        # Content-Language like "de-DE" / "nl-BE": take the region subtag.
        region = ""
        first = cl.split(",")[0].strip()
        if "-" in first:
            region = first.split("-")[-1].strip().upper()
        if region:
            response_agrees = region == req
            if region != req:
                notes.append(f"Content-Language region {region} != requested {req}")
    if cur_countries:
        # A country-pinning currency that includes the requested country counts as
        # corroboration; one that excludes it is a conflict signal.
        if req in cur_countries and len(cur_countries) == 1:
            response_agrees = True if response_agrees is None else response_agrees
        elif req not in cur_countries and len(cur_countries) == 1:
            response_agrees = False
            notes.append(
                f"observed currency pins {cur_countries[0]} != requested {req}"
            )

    # Combine into the agreement verdict.
    if exit_agrees is False or response_agrees is False:
        agreement = "CONFLICT"
    elif exit_agrees is True and response_agrees is True:
        agreement = "CONFIRMED"
    elif exit_agrees is True:
        agreement = "EXIT_ONLY"
    elif exit_agrees is None and response_agrees is True:
        # No network attribution but the server served the requested locale.
        agreement = "RESPONSE_ONLY"
    else:
        agreement = "UNATTRIBUTED"

    return GeoAttribution(
        requested_country=req,
        exit_ip=exit_ip,
        proxy_reported_country=proxy_reported_country.upper() if proxy_reported_country else None,
        rir_country=rir_cc,
        rir_registry=rir_reg,
        response_geo_signals=geo_headers,
        currency_observed=currency_observed.upper() if currency_observed else None,
        currency_consistent_countries=cur_countries,
        agreement=agreement,
        notes=notes,
    )
