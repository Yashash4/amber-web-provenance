"""Pure classified-retry policy tests (the Python port of PR #155).

The retry policy that lets a multi-geo same-second capture batch survive a
transient gateway blip is kept PURE (no network, no real sleeping, injected
``now_ms``/``rng``) so it is table-testable in isolation, exactly like the JS
original it ports. These tests mirror ``test/retry-utils.test.js`` upstream and
add the Python-specific transport-exception classification path Amber's
integration actually uses.
"""

from __future__ import annotations

import errno

import pytest
import requests

from amber.capture import retry

# A fixed clock so HTTP-date Retry-After cases are deterministic.
# 2026-01-19T20:51:08Z in epoch milliseconds.
NOW_MS = 1768855868000.0


# --------------------------------------------------------------------------- #
# classify_status taxonomy (table-driven, faithful to #155's OUTCOME map).
# --------------------------------------------------------------------------- #
_CLASSIFY_STATUS_CASES = [
    ("200 success", 200, None, retry.OUTCOME_SUCCESS, False, None),
    ("204 success", 204, None, retry.OUTCOME_SUCCESS, False, None),
    ("301 redirect", 301, None, retry.OUTCOME_REDIRECT, False, None),
    ("307 redirect", 307, None, retry.OUTCOME_REDIRECT, False, None),
    ("400 client error terminal", 400, None, retry.OUTCOME_CLIENT_ERROR, False, None),
    ("401 client error terminal", 401, None, retry.OUTCOME_CLIENT_ERROR, False, None),
    ("404 client error terminal", 404, None, retry.OUTCOME_CLIENT_ERROR, False, None),
    ("403 blocked terminal", 403, None, retry.OUTCOME_BLOCKED, False, None),
    ("451 blocked terminal", 451, None, retry.OUTCOME_BLOCKED, False, None),
    ("408 retryable", 408, None, retry.OUTCOME_RETRYABLE, True, None),
    ("425 retryable", 425, None, retry.OUTCOME_RETRYABLE, True, None),
    ("500 retryable", 500, None, retry.OUTCOME_RETRYABLE, True, None),
    ("502 gateway retryable (issue #104)", 502, None, retry.OUTCOME_RETRYABLE, True, None),
    ("503 retryable", 503, None, retry.OUTCOME_RETRYABLE, True, None),
    ("504 gateway timeout retryable (issue #104)", 504, None, retry.OUTCOME_RETRYABLE, True, None),
    ("599 unenumerated 5xx is retryable", 599, None, retry.OUTCOME_RETRYABLE, True, None),
    ("429 rate_limited retryable", 429, None, retry.OUTCOME_RATE_LIMITED, True, None),
    (
        "429 surfaces numeric Retry-After",
        429,
        {"retry-after": "2"},
        retry.OUTCOME_RATE_LIMITED,
        True,
        2000,
    ),
    (
        "429 uppercase Retry-After header",
        429,
        {"Retry-After": "5"},
        retry.OUTCOME_RATE_LIMITED,
        True,
        5000,
    ),
    (
        "503 HTTP-date Retry-After relative to now",
        503,
        {"retry-after": "Mon, 19 Jan 2026 20:51:18 GMT"},
        retry.OUTCOME_RETRYABLE,
        True,
        10000,
    ),
    ("no status is fatal", None, None, retry.OUTCOME_FATAL, False, None),
]


@pytest.mark.parametrize(
    "name,status,headers,outcome,retryable,retry_after_ms", _CLASSIFY_STATUS_CASES
)
def test_classify_status_taxonomy(name, status, headers, outcome, retryable, retry_after_ms):
    got = retry.classify_status(status, headers, NOW_MS)
    assert got.outcome == outcome, f"{name}: outcome {got.outcome} != {outcome}"
    assert got.retryable is retryable, f"{name}: retryable {got.retryable} != {retryable}"
    if retry_after_ms is not None:
        assert got.retry_after_ms == retry_after_ms, f"{name}: ra {got.retry_after_ms}"
    assert isinstance(got.reason, str) and got.reason


# --------------------------------------------------------------------------- #
# parse_retry_after (table-driven, faithful to #155's strictness).
# --------------------------------------------------------------------------- #
_PARSE_RETRY_AFTER_CASES = [
    ("None -> None", None, None),
    ("empty string -> None", "   ", None),
    ("integer seconds -> ms", "3", 3000),
    ("large integer seconds -> ms", "120", 120000),
    ("zero seconds -> 0", "0", 0),
    ("garbage -> None", "soon", None),
    # Strictness: fractional/negative/number-like junk must be None (fall back to
    # computed backoff), NOT 0 (an immediate retry via a permissive date parse).
    ("fractional seconds -> None (not 0)", "1.5", None),
    ("negative seconds -> None (not 0)", "-3", None),
    ("leading-plus -> None", "+5", None),
    ("trailing junk -> None", "5s", None),
    ("date-shaped junk -> None", "Mon, not a date", None),
    ("future HTTP-date -> positive ms", "Mon, 19 Jan 2026 20:51:18 GMT", 10000),
    ("past HTTP-date clamps to 0", "Mon, 19 Jan 2026 20:51:00 GMT", 0),
]


@pytest.mark.parametrize("name,value,expected", _PARSE_RETRY_AFTER_CASES)
def test_parse_retry_after(name, value, expected):
    got = retry.parse_retry_after(value, NOW_MS)
    assert got == expected, f"{name}: got {got} expected {expected}"


# --------------------------------------------------------------------------- #
# compute_backoff (table-driven, faithful to #155, injected rng).
# --------------------------------------------------------------------------- #
# Short alias so the (attempt, opts, retry_after_ms, rng, expected) table stays
# under the line-length limit while remaining table-driven like #155's suite.
_Opts = retry.BackoffOpts
_R0 = lambda: 0.0  # noqa: E731 - injected deterministic rng for jitter cases
_R1 = lambda: 1.0  # noqa: E731

_BACKOFF_CASES = [
    ("no jitter attempt 0 -> base", 0, _Opts(base_ms=500, jitter="none"), None, None, 500),
    ("no jitter attempt 1 -> base*factor", 1, _Opts(base_ms=500, jitter="none"), None, None, 1000),
    ("no jitter attempt 3 -> base*f^3", 3, _Opts(base_ms=500, jitter="none"), None, None, 4000),
    ("no jitter caps at max", 10, _Opts(max_ms=30000, jitter="none"), None, None, 30000),
    ("retry_after overrides exponential", 5, _Opts(base_ms=500, jitter="none"), 2000, None, 2000),
    ("retry_after clamped to max_ms", 0, _Opts(max_ms=30000, jitter="none"), 120000, None, 30000),
    ("full jitter rng=0 -> 0", 2, _Opts(base_ms=500, jitter="full"), None, _R0, 0),
    ("full jitter rng=1 -> capped", 2, _Opts(base_ms=500, jitter="full"), None, _R1, 2000),
    ("equal jitter rng=0 -> half capped", 2, _Opts(base_ms=500, jitter="equal"), None, _R0, 1000),
    ("equal jitter rng=1 -> full capped", 2, _Opts(base_ms=500, jitter="equal"), None, _R1, 2000),
    ("negative attempt floored to 0", -3, _Opts(base_ms=500, jitter="none"), None, None, 500),
    ("defaults applied when base opts none", 0, _Opts(jitter="none"), None, None, 500),
]


@pytest.mark.parametrize("name,attempt,opts,retry_after_ms,rng,expected", _BACKOFF_CASES)
def test_compute_backoff(name, attempt, opts, retry_after_ms, rng, expected):
    rng = rng or (lambda: 0.5)
    got = retry.compute_backoff(attempt, opts, rng, retry_after_ms=retry_after_ms)
    assert got == expected, f"{name}: got {got} expected {expected}"


def test_full_jitter_stays_within_zero_and_capped():
    """Full jitter must always land in [0, capped] across the rng range."""
    opts = retry.BackoffOpts(base_ms=500, factor=2, max_ms=30000, jitter="full")
    for r in (0.0, 0.01, 0.25, 0.5, 0.75, 0.99, 1.0):
        delay = retry.compute_backoff(3, opts, lambda r=r: r)
        assert 0 <= delay <= 4000, f"delay {delay} out of [0, 4000] for rng={r}"


def test_backoff_is_deterministic_under_injected_rng():
    """Same attempt + same injected rng -> identical delay, every call."""
    opts = retry.BackoffOpts(base_ms=500, factor=2, jitter="full")
    rng = lambda: 0.37  # noqa: E731
    a = retry.compute_backoff(2, opts, rng)
    b = retry.compute_backoff(2, opts, rng)
    assert a == b == round(0.37 * 2000)


# --------------------------------------------------------------------------- #
# should_retry budget + delay (table-driven, faithful to #155).
# --------------------------------------------------------------------------- #
def test_should_retry_within_budget_retries():
    c = retry.Classification(retry.OUTCOME_RETRYABLE, 502, None, True, "x")
    d = retry.should_retry(c, 0, 3, retry.BackoffOpts(jitter="none"), lambda: 0.5)
    assert d.retry is True


def test_should_retry_budget_exhausted_stops():
    c = retry.Classification(retry.OUTCOME_RETRYABLE, 502, None, True, "x")
    d = retry.should_retry(c, 3, 3, retry.BackoffOpts(jitter="none"), lambda: 0.5)
    assert d.retry is False


def test_should_retry_non_retryable_never_retries():
    c = retry.Classification(retry.OUTCOME_BLOCKED, 403, None, False, "x")
    d = retry.should_retry(c, 0, 3, retry.BackoffOpts(jitter="none"), lambda: 0.5)
    assert d.retry is False


def test_should_retry_missing_classification_never_retries():
    d = retry.should_retry(None, 0, 3, retry.BackoffOpts(jitter="none"), lambda: 0.5)
    assert d.retry is False


def test_should_retry_honors_classification_retry_after():
    c = retry.Classification(retry.OUTCOME_RATE_LIMITED, 429, 2000, True, "x")
    d = retry.should_retry(c, 0, 3, retry.BackoffOpts(max_ms=30000, jitter="none"), lambda: 0.5)
    assert d.retry is True
    assert d.delay_ms == 2000


# --------------------------------------------------------------------------- #
# classify_transport_error: the path Amber's integration actually uses. A THROWN
# transport exception (no capturable response) is classified transient vs fatal.
# --------------------------------------------------------------------------- #
def test_connection_reset_is_retryable():
    c = retry.classify_transport_error(ConnectionResetError(errno.ECONNRESET, "reset"))
    assert c.retryable is True
    assert c.outcome == retry.OUTCOME_RETRYABLE


def test_timeout_error_is_retryable():
    c = retry.classify_transport_error(TimeoutError("read timed out"))
    assert c.retryable is True


def test_socket_timeout_is_retryable():
    # socket.timeout is an alias of the builtin TimeoutError (Python 3.10+); use
    # the builtin so a real read-timeout shape is classified retryable.
    c = retry.classify_transport_error(TimeoutError("timed out"))
    assert c.retryable is True


def test_requests_connection_error_is_retryable():
    c = retry.classify_transport_error(requests.exceptions.ConnectionError("conn refused"))
    assert c.retryable is True


def test_requests_read_timeout_is_retryable():
    c = retry.classify_transport_error(requests.exceptions.ReadTimeout("read timed out"))
    assert c.retryable is True


def test_requests_proxy_error_is_retryable():
    """A transient proxy tunnel blip (the 502/504/reset surfaced via the proxy)
    is retryable on the same session."""
    c = retry.classify_transport_error(
        requests.exceptions.ProxyError("Tunnel connection failed: 502 Bad Gateway")
    )
    assert c.retryable is True


def test_wrapped_econnreset_in_cause_chain_is_retryable():
    """requests buries the socket errno several layers deep; the chained cause
    must still be recognized as a retryable reset."""
    inner = ConnectionResetError(errno.ECONNRESET, "reset")
    wrapper = requests.exceptions.RequestException("boom")
    wrapper.__cause__ = inner
    c = retry.classify_transport_error(wrapper)
    assert c.retryable is True


def test_unknown_transport_error_is_fatal_not_silently_retried():
    """An unrecognized transport failure is FATAL (surfaced), never silently
    retried into a hopeless loop."""

    class _WeirdError(Exception):
        pass

    c = retry.classify_transport_error(_WeirdError("nope"))
    assert c.retryable is False
    assert c.outcome == retry.OUTCOME_FATAL
