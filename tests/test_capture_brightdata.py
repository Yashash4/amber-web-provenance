"""Bright Data batch-timestamp honesty tests.

The "same second" claim is a legal weapon, so the receipt must be REAL: a batch
whose actual wall-clock fetches span more than a second must report
``same_second_batch=false``. These tests exercise the pure spread logic
(:func:`brightdata.stamp_batch_timestamps`) with INJECTED fetch instants — no
live Bright Data, no network — and confirm the floor reads the same verdict off
the stamped records.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from amber.capture import brightdata, floor
from amber.capture.record import CaptureRecord

URL = "https://shop.example/product/amber-hero-001"
_BASE = datetime(2026, 5, 29, 0, 0, 1, tzinfo=UTC)


def _rec(cid: str, country: str = "DE") -> CaptureRecord:
    """A minimal valid record with a deliberately bogus initial requested_at so
    the test proves stamp_batch_timestamps OVERWRITES it from the real instants."""
    return CaptureRecord(
        capture_id=cid,
        url=URL,
        requested_country=country,
        session_id=f"s-{cid}",
        exit_ip="91.10.0.1",
        requested_at="UNSET",
        http_status=200,
        headers={"content-type": "application/json"},
        body=b'{"sku":"AMBER-HERO-001","price":"129.99","currency":"EUR"}',
    )


def test_within_one_second_spread_is_same_second_true():
    """Real spread <= 1s -> one canonical second on every record -> same_second."""
    recs = [_rec("a"), _rec("b"), _rec("c")]
    fetched = [
        _BASE,
        _BASE + timedelta(milliseconds=400),
        _BASE + timedelta(milliseconds=900),
    ]
    same_second = brightdata.stamp_batch_timestamps(recs, fetched)
    assert same_second is True
    stamps = {r.requested_at for r in recs}
    assert stamps == {"2026-05-29T00:00:01Z"}
    # The floor derives the SAME verdict from the distinct-timestamp count.
    facts = floor.build_facts(URL, recs)
    assert facts["same_second_batch"] is True


def test_sub_second_spread_across_a_second_boundary_is_still_same_second():
    """A 0.2s real spread that straddles a second boundary (…01.9 -> …02.1) must
    STILL report same_second — the truth is the spread, not the wall-clock second.
    Naive per-capture second-truncation would have wrongly read this as false."""
    recs = [_rec("a"), _rec("b")]
    fetched = [
        _BASE + timedelta(milliseconds=900),  # 00:00:01.900
        _BASE + timedelta(milliseconds=1100),  # 00:00:02.100  (0.2s later)
    ]
    same_second = brightdata.stamp_batch_timestamps(recs, fetched)
    assert same_second is True
    assert {r.requested_at for r in recs} == {"2026-05-29T00:00:01Z"}
    assert floor.build_facts(URL, recs)["same_second_batch"] is True


def test_over_one_second_spread_is_reported_false_not_hidden():
    """Real spread > 1s -> each record keeps its OWN real second -> the floor
    honestly reports same_second_batch=false (the branch the docstring promises)."""
    recs = [_rec("a"), _rec("b"), _rec("c")]
    fetched = [
        _BASE,
        _BASE + timedelta(seconds=1.5),
        _BASE + timedelta(seconds=3.0),
    ]
    same_second = brightdata.stamp_batch_timestamps(recs, fetched)
    assert same_second is False
    stamps = sorted({r.requested_at for r in recs})
    assert stamps == [
        "2026-05-29T00:00:01Z",
        "2026-05-29T00:00:02Z",
        "2026-05-29T00:00:04Z",
    ]
    assert floor.build_facts(URL, recs)["same_second_batch"] is False


def test_exactly_one_second_spread_is_same_second_inclusive():
    """The boundary is inclusive: an exactly-1.0s spread is same-second."""
    recs = [_rec("a"), _rec("b")]
    fetched = [_BASE, _BASE + timedelta(seconds=1.0)]
    assert brightdata.stamp_batch_timestamps(recs, fetched) is True
    assert {r.requested_at for r in recs} == {"2026-05-29T00:00:01Z"}


def test_just_over_one_second_spread_is_not_same_second():
    """A 1.001s spread is over the floor -> false (no rounding the claim up)."""
    recs = [_rec("a"), _rec("b")]
    fetched = [_BASE, _BASE + timedelta(seconds=1.001)]
    assert brightdata.stamp_batch_timestamps(recs, fetched) is False


def test_length_mismatch_is_surfaced_not_swallowed():
    recs = [_rec("a"), _rec("b")]
    with pytest.raises(brightdata.CaptureError):
        brightdata.stamp_batch_timestamps(recs, [_BASE])


def test_empty_batch_is_trivially_same_second():
    assert brightdata.stamp_batch_timestamps([], []) is True


# --------------------------------------------------------------------------- #
# dispatched_same_second: the honest "DISPATCHED within a second" verdict.
# --------------------------------------------------------------------------- #
def _rec_dispatched(cid: str, dispatched_at: str, country: str = "DE") -> CaptureRecord:
    rec = _rec(cid, country)
    rec.dispatched_at = dispatched_at
    return rec


def test_dispatched_same_second_true_when_launches_cluster():
    """Concurrent dispatch: launch instants within 1s -> dispatched_same_second."""
    recs = [
        _rec_dispatched("a", "2026-05-29T00:00:01.000Z"),
        _rec_dispatched("b", "2026-05-29T00:00:01.030Z"),
        _rec_dispatched("c", "2026-05-29T00:00:01.080Z"),
    ]
    assert brightdata.dispatched_same_second(recs) is True


def test_dispatched_same_second_true_across_a_second_boundary():
    """A 0.2s dispatch spread straddling a boundary is still same-second."""
    recs = [
        _rec_dispatched("a", "2026-05-29T00:00:01.900Z"),
        _rec_dispatched("b", "2026-05-29T00:00:02.100Z"),
    ]
    assert brightdata.dispatched_same_second(recs) is True


def test_dispatched_same_second_false_when_launches_span_over_a_second():
    """Sequential dispatch (the OLD behaviour) spreads over a second -> false,
    surfaced honestly rather than overclaimed."""
    recs = [
        _rec_dispatched("a", "2026-05-29T00:00:01.000Z"),
        _rec_dispatched("b", "2026-05-29T00:00:03.500Z"),
    ]
    assert brightdata.dispatched_same_second(recs) is False


def test_dispatched_same_second_exactly_one_second_is_inclusive():
    recs = [
        _rec_dispatched("a", "2026-05-29T00:00:01.000Z"),
        _rec_dispatched("b", "2026-05-29T00:00:02.000Z"),
    ]
    assert brightdata.dispatched_same_second(recs) is True


def test_dispatched_same_second_just_over_one_second_is_false():
    recs = [
        _rec_dispatched("a", "2026-05-29T00:00:01.000Z"),
        _rec_dispatched("b", "2026-05-29T00:00:02.001Z"),
    ]
    assert brightdata.dispatched_same_second(recs) is False


def test_dispatched_same_second_empty_is_trivially_true():
    assert brightdata.dispatched_same_second([]) is True


def test_dispatched_same_second_missing_stamp_is_surfaced_not_assumed():
    """A record with no dispatch stamp must RAISE — never silently read as true
    (that would fabricate a simultaneity claim)."""
    recs = [
        _rec_dispatched("a", "2026-05-29T00:00:01.000Z"),
        _rec("b"),  # no dispatched_at
    ]
    with pytest.raises(brightdata.CaptureError):
        brightdata.dispatched_same_second(recs)


# --------------------------------------------------------------------------- #
# The floor surfaces the dispatch fact honestly (both true and unknown cases).
# --------------------------------------------------------------------------- #
def test_floor_reports_dispatched_same_second_true_and_lists_seconds():
    recs = [
        _rec_dispatched("de-01", "2026-05-29T00:00:01.000Z", "DE"),
        _rec_dispatched("be-01", "2026-05-29T00:00:01.050Z", "BE"),
    ]
    facts = floor.build_facts(URL, recs)
    assert facts["dispatched_same_second"] is True
    assert facts["dispatched_at_values"] == ["2026-05-29T00:00:01Z"]


def test_floor_reports_dispatched_same_second_false_with_distinct_seconds():
    recs = [
        _rec_dispatched("de-01", "2026-05-29T00:00:01.000Z", "DE"),
        _rec_dispatched("be-01", "2026-05-29T00:00:05.000Z", "BE"),
    ]
    facts = floor.build_facts(URL, recs)
    assert facts["dispatched_same_second"] is False
    assert facts["dispatched_at_values"] == [
        "2026-05-29T00:00:01Z",
        "2026-05-29T00:00:05Z",
    ]


def test_floor_dispatch_fact_is_null_when_no_stamps_present():
    """Offline floor fixtures carry no dispatch stamp; the fact is null (unknown),
    never fabricated as true."""
    facts = floor.build_facts(URL, [_rec("a"), _rec("b")])
    assert facts["dispatched_same_second"] is None
    assert facts["dispatched_at_values"] == []


def test_floor_dispatch_fact_partial_stamp_is_surfaced():
    recs = [_rec_dispatched("a", "2026-05-29T00:00:01.000Z"), _rec("b")]
    with pytest.raises(brightdata.CaptureError):
        floor.build_facts(URL, recs)
