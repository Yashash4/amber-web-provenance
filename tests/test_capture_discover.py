"""Hero-SKU discovery scoring/ranking tests — honest no-finding, never a forced
pick. Exercised offline against constructed floor facts (the live capture needs
BD creds; the ranking logic does not)."""

from __future__ import annotations

from amber.capture import discover, floor
from amber.capture.record import CaptureRecord

URL = "https://shop.example/p/x"
GTIN = "4006381333931"
DE_IPS = ["91.10.0.1", "91.10.0.2", "91.10.0.3"]
BE_IPS = ["91.176.0.1", "91.176.0.2", "91.176.0.3"]


def _body(price, gtin=GTIN, avail="InStock"):
    return (
        b'{"gtin":"' + gtin.encode() + b'","price":"' + str(price).encode() + b'",'
        b'"currency":"EUR","availability":"' + avail.encode() + b'",'
        b'"description":"long enough product body to avoid the degenerate gate"}'
    )


def _rec(cid, country, sess, ip, body, status=200):
    return CaptureRecord(
        capture_id=cid, url=URL, requested_country=country, session_id=sess,
        exit_ip=ip, requested_at="2026-05-29T00:00:01Z", http_status=status,
        headers={"content-type": "application/json"}, body=body,
    )


def _delta_facts(de_price, be_price, gtin_be=GTIN):
    recs = []
    for i, ip in enumerate(DE_IPS):
        recs.append(_rec(f"de-{i+1}", "DE", f"sd{i}", ip, _body(de_price)))
    for i, ip in enumerate(BE_IPS):
        recs.append(_rec(f"be-{i+1}", "BE", f"sb{i}", ip, _body(be_price, gtin=gtin_be)))
    return floor.build_facts(URL, recs)


def test_clean_delta_qualifies():
    # DE 149.99 vs BE 129.99 (different gross) -> a real net delta, GTIN match.
    facts = _delta_facts("149.99", "129.99")
    cand = discover.score_candidate(URL, facts)
    assert cand.disqualified is False
    assert cand.finding_kind == "NET_OF_TAX_PRICE_DELTA"
    assert cand.score > 0


def test_no_net_delta_is_disqualified_control():
    # Same gross both -> after VAT there IS a small net delta (different VAT), so
    # to get a true NO_NET_DELTA we use prices that net out equal is hard; instead
    # use a single country so there is no cross-country comparison.
    recs = [_rec(f"de-{i+1}", "DE", f"sd{i}", DE_IPS[i], _body("129.99")) for i in range(3)]
    facts = floor.build_facts(URL, recs)
    cand = discover.score_candidate(URL, facts)
    assert cand.disqualified is True
    assert cand.finding_kind == "NONE"


def test_unverified_identity_disqualifies_delta():
    facts = _delta_facts("149.99", "129.99", gtin_be="5010019640161")  # different GTIN
    cand = discover.score_candidate(URL, facts)
    assert cand.disqualified is True
    assert any("identity" in r.lower() for r in cand.reasons)


def test_within_country_disagreement_disqualifies_delta():
    recs = []
    recs.append(_rec("de-1", "DE", "sd0", DE_IPS[0], _body("149.99")))
    recs.append(_rec("de-2", "DE", "sd1", DE_IPS[1], _body("139.99")))  # DE exits disagree
    recs.append(_rec("de-3", "DE", "sd2", DE_IPS[2], _body("149.99")))
    for i, ip in enumerate(BE_IPS):
        recs.append(_rec(f"be-{i+1}", "BE", f"sb{i}", ip, _body("129.99")))
    facts = floor.build_facts(URL, recs)
    cand = discover.score_candidate(URL, facts)
    assert cand.disqualified is True
    assert any("within-country" in r.lower() for r in cand.reasons)


def test_access_denial_scores_highest():
    recs = [
        _rec("de-1", "DE", "sd0", DE_IPS[0], _body("129.99")),
        _rec("de-2", "DE", "sd1", DE_IPS[1], _body("129.99")),
        _rec("be-1", "BE", "sb0", BE_IPS[0],
             b"<html>We do not ship to your country.</html>", status=451),
        _rec("be-2", "BE", "sb1", BE_IPS[1],
             b"<html>We do not ship to your country.</html>", status=451),
    ]
    facts = floor.build_facts(URL, recs)
    cand = discover.score_candidate(URL, facts)
    assert cand.finding_kind == "ACCESS_OR_PAYMENT_DENIAL"
    assert cand.disqualified is False
    assert cand.score == 100.0


def test_rank_picks_denial_over_delta():
    delta = discover.score_candidate("u1", _delta_facts("149.99", "129.99"), "delta-sku")
    denial_recs = [
        _rec("de-1", "DE", "sd0", DE_IPS[0], _body("129.99")),
        _rec("de-2", "DE", "sd1", DE_IPS[1], _body("129.99")),
        _rec("be-1", "BE", "sb0", BE_IPS[0], b"<html>We do not ship to your country.</html>", 451),
        _rec("be-2", "BE", "sb1", BE_IPS[1], b"<html>We do not ship to your country.</html>", 451),
    ]
    denial = discover.score_candidate("u2", floor.build_facts("u2", denial_recs), "denial-sku")
    result = discover.rank([delta, denial])
    assert result.no_finding is False
    assert result.hero.finding_kind == "ACCESS_OR_PAYMENT_DENIAL"


def test_rank_no_finding_when_all_disqualified():
    single = [_rec(f"de-{i+1}", "DE", f"sd{i}", DE_IPS[i], _body("129.99")) for i in range(3)]
    cand = discover.score_candidate("u", floor.build_facts("u", single))
    result = discover.rank([cand])
    assert result.no_finding is True
    assert result.hero is None
    assert "NO candidate" in result.message
