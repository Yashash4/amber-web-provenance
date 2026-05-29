"""The deterministic measurement-validity floor -> facts.json (Layer-1, signed).

This is the analysis core of Component 2. Given the same-second batch of
:class:`~amber.capture.record.CaptureRecord`s for ONE product URL across two
countries (Germany, Belgium) plus the within-country control (several distinct
residential exits per country), it computes — deterministically, NO LLM — the
Layer-1 facts that get sealed into the signed packet:

  * per-capture extraction (price/currency/availability/GTIN), soft-block
    verdict, factual state, and two-source geo-attribution;
  * the net-of-tax spread (gross AND net, using the sourced VAT table);
  * the SKU-identity confidence (GTIN match across captures);
  * the within-country control: intra-country price agreement vs the
    cross-country delta;
  * the headline comparison: the cross-country net-of-tax delta or a real
    access/payment denial.

It outputs a ``facts.json`` dict (schema ``amber/facts@2``) suitable for
:func:`amber.packet.seal_packet`. Every number is a string (no float drift); the
VAT rate + source travel inline; the geo claim travels with its two-source
evidence. Nothing is invented: a capture with no extractable price contributes a
state (often INCONCLUSIVE) but never a fabricated figure.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from amber.capture import extract, geoattr, identity, softblock, state, vat
from amber.capture.record import CaptureRecord

FACTS_SCHEMA = "amber/facts@2"


@dataclass
class PerCaptureFact:
    """The fully analysed Layer-1 fact for a single capture."""

    capture_id: str
    requested_country: str
    session_id: str
    exit_ip: str
    extracted: extract.Extracted
    soft_block: softblock.SoftBlockResult
    state_result: state.StateResult
    attribution: geoattr.GeoAttribution
    vat_rate: vat.VatRate | None
    price_gross: Decimal | None
    price_net: Decimal | None

    def as_fact(self) -> dict:
        return {
            "capture_id": self.capture_id,
            "requested_country": self.requested_country,
            "session_id": self.session_id,
            "exit_ip": self.exit_ip,
            "extracted": self.extracted.as_fact(),
            "state": self.state_result.as_fact(),
            "geo_attribution": self.attribution.as_fact(),
            "vat_rate": self.vat_rate.as_fact() if self.vat_rate else "VAT_RATE_UNAVAILABLE",
            "price_gross": format(self.price_gross, "f") if self.price_gross is not None else None,
            "price_net": format(self.price_net, "f") if self.price_net is not None else None,
        }


def analyse_capture(
    record: CaptureRecord,
    *,
    category: str = vat.CATEGORY_STANDARD,
) -> PerCaptureFact:
    """Run the full deterministic analysis on one capture record."""
    headers = record.headers
    body = record.body

    extracted = extract.extract(body, headers)
    sb = softblock.detect(record.http_status, headers, body)
    st = state.classify(record.http_status, headers, body, extracted, sb)
    attribution = geoattr.attribute(
        record.requested_country,
        record.exit_ip,
        headers,
        proxy_reported_country=record.proxy_reported_country,
        currency_observed=extracted.currency,
    )

    # Net-of-tax only when a gross price was actually extracted AND the state is
    # PURCHASABLE (a price on a blocked/soft-blocked page is not a real offer).
    rate = vat.lookup_rate(record.requested_country, category)
    gross = extracted.price if st.state == state.PURCHASABLE else None
    net: Decimal | None = None
    if gross is not None and rate is not None:
        net = vat.net_of_tax(gross, rate.rate)

    return PerCaptureFact(
        capture_id=record.capture_id,
        requested_country=record.requested_country.upper(),
        session_id=record.session_id,
        exit_ip=record.exit_ip,
        extracted=extracted,
        soft_block=sb,
        state_result=st,
        attribution=attribution,
        vat_rate=rate,
        price_gross=gross,
        price_net=net,
    )


def _country_net_prices(facts: list[PerCaptureFact]) -> dict[str, list[tuple[str, Decimal]]]:
    """Group (session_id, net_price) by country, PURCHASABLE captures only."""
    grouped: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    for f in facts:
        if f.state_result.state == state.PURCHASABLE and f.price_net is not None:
            grouped[f.requested_country].append((f.session_id, f.price_net))
    return grouped


def within_country_control(facts: list[PerCaptureFact]) -> dict:
    """Compute the within-country control: intra-country agreement per country.

    For each country with >=2 PURCHASABLE captures, report whether the distinct
    residential exits AGREE on the net price (the spread between min and max
    intra-country net prices). A near-zero intra-country spread is the control
    that makes a non-zero CROSS-country delta meaningful: it shows the
    cross-country difference is not exit-IP noise.
    """
    grouped = _country_net_prices(facts)
    per_country = []
    for country in sorted(grouped):
        prices = [p for _sid, p in grouped[country]]
        sessions = [sid for sid, _p in grouped[country]]
        lo, hi = min(prices), max(prices)
        spread = vat.quantize_money(hi - lo)
        per_country.append(
            {
                "country": country,
                "n_purchasable_exits": len(prices),
                "session_ids": sessions,
                "net_prices": [format(p, "f") for p in prices],
                "net_min": format(lo, "f"),
                "net_max": format(hi, "f"),
                "intra_country_spread": format(spread, "f"),
                "agreement": "AGREE" if spread == 0 else "DISAGREE",
            }
        )
    return {
        "per_country": per_country,
        "all_intra_country_agree": all(
            c["agreement"] == "AGREE" for c in per_country
        )
        if per_country
        else False,
    }


def _country_representative_net(facts: list[PerCaptureFact]) -> dict[str, Decimal]:
    """One representative net price per country = the min net across its exits.

    Using the min (rather than a mean) is deterministic and conservative: the
    cross-country delta is computed as the smallest net price a buyer in the more
    expensive country could have gotten vs the cheaper country, so the reported
    gap is never inflated by an outlier exit.
    """
    grouped = _country_net_prices(facts)
    return {c: min(p for _s, p in pairs) for c, pairs in grouped.items() if pairs}


def cross_country_comparison(facts: list[PerCaptureFact]) -> dict:
    """The headline comparison across the two countries.

    Produces, deterministically, EITHER:
      * a net-of-tax price delta (when >=2 countries are PURCHASABLE with prices), OR
      * an access/payment-denial finding (when a country's state is GEO_BLOCKED
        while another is PURCHASABLE).
    Never both as the "headline"; both are recorded if present, with a
    ``primary_finding`` token naming which fired. INCONCLUSIVE countries are
    reported but never silently treated as a denial.
    """
    rep = _country_representative_net(facts)
    states_by_country: dict[str, set[str]] = defaultdict(set)
    gross_by_country: dict[str, list[Decimal]] = defaultdict(list)
    for f in facts:
        states_by_country[f.requested_country].add(f.state_result.state)
        if f.price_gross is not None:
            gross_by_country[f.requested_country].append(f.price_gross)

    # Net delta across the two cheapest-representative countries.
    net_delta_finding = None
    if len(rep) >= 2:
        ordered = sorted(rep.items(), key=lambda kv: kv[1])
        cheap_country, cheap_net = ordered[0]
        exp_country, exp_net = ordered[-1]
        delta = vat.quantize_money(exp_net - cheap_net)
        # Representative gross figures for transparency (min gross per country).
        cheap_gross = (
            min(gross_by_country[cheap_country]) if gross_by_country[cheap_country] else None
        )
        exp_gross = min(gross_by_country[exp_country]) if gross_by_country[exp_country] else None
        gross_delta = (
            vat.quantize_money(exp_gross - cheap_gross)
            if cheap_gross is not None and exp_gross is not None
            else None
        )
        net_delta_finding = {
            "cheaper_country": cheap_country,
            "more_expensive_country": exp_country,
            "cheaper_net": format(cheap_net, "f"),
            "more_expensive_net": format(exp_net, "f"),
            "net_of_tax_delta": format(delta, "f"),
            "gross_delta": format(gross_delta, "f") if gross_delta is not None else None,
            "delta_is_nonzero": delta != 0,
        }

    # Access/payment denial: one country GEO_BLOCKED while another PURCHASABLE.
    denial_countries = sorted(
        c for c, sts in states_by_country.items() if state.GEO_BLOCKED in sts
    )
    purchasable_countries = sorted(
        c for c, sts in states_by_country.items() if state.PURCHASABLE in sts
    )
    denial_finding = None
    if denial_countries and purchasable_countries:
        denial_finding = {
            "geo_blocked_countries": denial_countries,
            "purchasable_countries": purchasable_countries,
        }

    # Decide the primary finding.
    if denial_finding is not None:
        primary = "ACCESS_OR_PAYMENT_DENIAL"
    elif net_delta_finding is not None and net_delta_finding["delta_is_nonzero"]:
        primary = "NET_OF_TAX_PRICE_DELTA"
    elif net_delta_finding is not None:
        primary = "NO_NET_DELTA"  # prices agree net-of-tax (a control / non-finding)
    else:
        primary = "INCONCLUSIVE"

    return {
        "primary_finding": primary,
        "net_delta": net_delta_finding,
        "access_denial": denial_finding,
        "per_country_states": {c: sorted(s) for c, s in sorted(states_by_country.items())},
    }


def build_facts(
    url: str,
    records: list[CaptureRecord],
    *,
    category: str = vat.CATEGORY_STANDARD,
    sku_label: str | None = None,
) -> dict:
    """Build the complete ``facts.json`` dict from a batch of capture records.

    The returned dict is the Layer-1 signed-facts artifact (schema
    ``amber/facts@2``). Pass it, with the same records' bodies, to
    :func:`amber.packet.seal_packet`.
    """
    if not records:
        raise ValueError("build_facts: at least one capture record is required")

    per_capture = [analyse_capture(r, category=category) for r in records]

    # SKU identity across all captures (GTIN match -> the comparison is valid).
    id_inputs = [
        identity.IdentityInput(capture_id=f.capture_id, gtin=f.extracted.gtin)
        for f in per_capture
    ]
    id_result = identity.assess(id_inputs)

    # Same-second discipline: record the distinct requested_at values so a
    # verifier can confirm the batch was a same-second measurement (we report it
    # as a fact rather than asserting it — restraint over claim).
    timestamps = sorted({r.requested_at for r in records})

    facts = {
        "schema": FACTS_SCHEMA,
        "url": url,
        "sku_label": sku_label,
        "category": category,
        "capture_count": len(records),
        "countries": sorted({r.requested_country.upper() for r in records}),
        "requested_at_values": timestamps,
        "same_second_batch": len(timestamps) == 1,
        "vat_table_note": (
            "Net-of-tax computed with the committed sourced VAT table "
            "(amber/capture/vat.py); each per-capture fact carries the rate + "
            "source it was computed with. net = gross / (1 + rate)."
        ),
        "sku_identity": id_result.as_fact(),
        "per_capture": [f.as_fact() for f in per_capture],
        "within_country_control": within_country_control(per_capture),
        "cross_country_comparison": cross_country_comparison(per_capture),
    }
    return facts
