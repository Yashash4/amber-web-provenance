"""Measurement-floor tests: net-of-tax spread, within-country control, the
cross-country comparison, and the full floor -> seal_packet -> verify_packet
pipeline (GATE 2's deterministic half, exercised offline against constructed
capture records — real bytes, not a faked live capture).
"""

from __future__ import annotations

import pytest

from amber.capture import floor, identity, state
from amber.capture.harness import seal_from_records
from amber.capture.record import CaptureRecord
from amber.signer import generate_keypair

URL = "https://shop.example/product/amber-hero-001"
GTIN = "4006381333931"  # check-digit-valid EAN-13


def _body(price: str, *, gtin: str = GTIN, avail: str = "InStock", currency: str = "EUR") -> bytes:
    """A real JSON product body with enough bytes to clear the degenerate gate."""
    return (
        b'{"sku":"AMBER-HERO-001","gtin":"' + gtin.encode() + b'",'
        b'"price":"' + price.encode() + b'","currency":"' + currency.encode() + b'",'
        b'"availability":"' + avail.encode() + b'",'
        b'"description":"a normal product response body, long enough to not look '
        b'degenerate to the soft-block detector"}'
    )


def _rec(cid, country, session, ip, body, *, status=200, headers=None) -> CaptureRecord:
    return CaptureRecord(
        capture_id=cid,
        url=URL,
        requested_country=country,
        session_id=session,
        exit_ip=ip,
        requested_at="2026-05-29T00:00:01Z",
        http_status=status,
        headers=headers
        or {"content-type": "application/json", "content-language": f"xx-{country}"},
        body=body,
    )


# Real RIPE-snapshot DE/BE IPs so geo-attribution is genuine in the fixture.
DE_IPS = ["91.10.0.1", "91.10.0.2", "91.10.0.3"]
BE_IPS = ["91.176.0.1", "91.176.0.2", "91.176.0.3"]


def _de_be_records_same_gross() -> list[CaptureRecord]:
    """DE and BE both at the SAME gross 129.99 — the net-of-tax test: identical
    shelf price nets out DIFFERENTLY (DE 19% vs BE 21%), proving the floor
    subtracts the tax artifact rather than reporting it as a gap."""
    recs = []
    for i, ip in enumerate(DE_IPS):
        recs.append(_rec(f"de-{i+1:02d}", "DE", f"s-de-{i+1}", ip, _body("129.99")))
    for i, ip in enumerate(BE_IPS):
        recs.append(_rec(f"be-{i+1:02d}", "BE", f"s-be-{i+1}", ip, _body("129.99")))
    return recs


def test_net_of_tax_spread_from_identical_gross():
    facts = floor.build_facts(URL, _de_be_records_same_gross(), sku_label="AMBER-HERO-001")
    comp = facts["cross_country_comparison"]
    # Same gross price, but the NET differs because VAT differs.
    assert comp["primary_finding"] == "NET_OF_TAX_PRICE_DELTA"
    nd = comp["net_delta"]
    # net_DE = 129.99/1.19 = 109.24 ; net_BE = 129.99/1.21 = 107.43
    assert nd["cheaper_country"] == "BE"
    assert nd["more_expensive_country"] == "DE"
    assert nd["cheaper_net"] == "107.43"
    assert nd["more_expensive_net"] == "109.24"
    assert nd["net_of_tax_delta"] == "1.81"
    # The GROSS delta is ZERO (same shelf price) — the honest insight.
    assert nd["gross_delta"] == "0.00"


def test_within_country_control_agreement():
    facts = floor.build_facts(URL, _de_be_records_same_gross())
    wcc = facts["within_country_control"]
    assert wcc["all_intra_country_agree"] is True
    by_country = {c["country"]: c for c in wcc["per_country"]}
    assert by_country["DE"]["n_purchasable_exits"] == 3
    assert by_country["DE"]["agreement"] == "AGREE"
    assert by_country["DE"]["intra_country_spread"] == "0.00"
    assert by_country["BE"]["agreement"] == "AGREE"


def test_within_country_disagreement_flagged():
    """If one DE exit shows a different price, the control must report DISAGREE —
    making any cross-country delta suspect (exit noise, not a real gap)."""
    recs = _de_be_records_same_gross()
    # Corrupt one DE exit's price.
    recs[0] = _rec("de-01", "DE", "s-de-1", DE_IPS[0], _body("99.99"))
    facts = floor.build_facts(URL, recs)
    wcc = facts["within_country_control"]
    by_country = {c["country"]: c for c in wcc["per_country"]}
    assert by_country["DE"]["agreement"] == "DISAGREE"
    assert wcc["all_intra_country_agree"] is False


def test_sku_identity_match_in_facts():
    facts = floor.build_facts(URL, _de_be_records_same_gross())
    assert facts["sku_identity"]["confidence"] == identity.GTIN_MATCH


def test_mismatched_gtin_marks_identity_unverified():
    recs = _de_be_records_same_gross()
    recs[-1] = _rec("be-03", "BE", "s-be-3", BE_IPS[2], _body("129.99", gtin="5010019640161"))
    facts = floor.build_facts(URL, recs)
    assert facts["sku_identity"]["confidence"] == identity.SKU_IDENTITY_UNVERIFIED


def test_access_denial_is_primary_when_one_country_blocked():
    """One country GEO_BLOCKED (>=2 signals), the other PURCHASABLE -> the access
    denial is the primary finding (the access/payment-denial hero re-aim)."""
    recs = [
        _rec("de-01", "DE", "s-de-1", DE_IPS[0], _body("129.99")),
        _rec("de-02", "DE", "s-de-2", DE_IPS[1], _body("129.99")),
        # BE: 451 status + on-page geo-reason = 2 independent classes -> GEO_BLOCKED
        _rec(
            "be-01", "BE", "s-be-1", BE_IPS[0],
            b"<html><body>We do not ship to your country.</body></html>",
            status=451,
        ),
        _rec(
            "be-02", "BE", "s-be-2", BE_IPS[1],
            b"<html><body>We do not ship to your country.</body></html>",
            status=451,
        ),
    ]
    facts = floor.build_facts(URL, recs)
    comp = facts["cross_country_comparison"]
    assert comp["primary_finding"] == "ACCESS_OR_PAYMENT_DENIAL"
    assert "BE" in comp["access_denial"]["geo_blocked_countries"]
    assert "DE" in comp["access_denial"]["purchasable_countries"]


def test_softblock_country_stays_inconclusive_not_denial():
    """A soft-blocked BE must NOT become a denial — it's INCONCLUSIVE."""
    recs = [
        _rec("de-01", "DE", "s-de-1", DE_IPS[0], _body("129.99")),
        _rec("de-02", "DE", "s-de-2", DE_IPS[1], _body("129.99")),
        _rec(
            "be-01", "BE", "s-be-1", BE_IPS[0],
            b"<html><title>Just a moment...</title><div class='cf-challenge'>"
            b"not available in your country</div></html>",
            status=403,
        ),
    ]
    facts = floor.build_facts(URL, recs)
    comp = facts["cross_country_comparison"]
    assert comp["access_denial"] is None
    assert state.INCONCLUSIVE in comp["per_country_states"]["BE"]


def test_same_second_batch_flag():
    facts = floor.build_facts(URL, _de_be_records_same_gross())
    assert facts["same_second_batch"] is True
    assert facts["requested_at_values"] == ["2026-05-29T00:00:01Z"]


def test_build_facts_rejects_empty():
    with pytest.raises(ValueError):
        floor.build_facts(URL, [])


# --------------------------------------------------------------------------- #
# Full pipeline: floor -> seal_packet -> verify_packet (GATE 2 deterministic half)
# --------------------------------------------------------------------------- #


def test_floor_seal_verify_green(tmp_path):
    """The deterministic GATE 2: floor produces facts, seal builds a signed
    packet, verify_packet is GREEN against the pinned (test) signer key."""
    sk, pk = generate_keypair()
    records = _de_be_records_same_gross()
    out = tmp_path / "amber_packet"
    result = seal_from_records(out, URL, records, sk, trusted_pubkeys={pk})
    assert result.verify_ok is True
    # The signed facts contain the headline net-of-tax delta.
    assert result.facts["cross_country_comparison"]["net_delta"]["net_of_tax_delta"] == "1.81"


def test_sealed_facts_tamper_turns_red(tmp_path):
    """Editing a sealed net price flips verify to RED (facts.json is a Merkle leaf)."""
    import json

    from amber.packet import FACTS_FILE, verify_packet
    from amber.signer import canonical_json

    sk, pk = generate_keypair()
    out = tmp_path / "amber_packet"
    seal_from_records(out, URL, _de_be_records_same_gross(), sk, trusted_pubkeys={pk})
    assert verify_packet(out, expected_pubkeys={pk}).ok is True

    facts = json.loads((out / FACTS_FILE).read_bytes())
    facts["cross_country_comparison"]["net_delta"]["net_of_tax_delta"] = "999.99"
    (out / FACTS_FILE).write_bytes(canonical_json(facts))

    r = verify_packet(out, expected_pubkeys={pk})
    assert r.ok is False
    assert r.broken_node == FACTS_FILE
