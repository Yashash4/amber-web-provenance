"""Bright Data proxy-transport tests (the requests-based fix).

Component 2's residential capture goes through Bright Data's port-33335
super-proxy, which (a) requires ``Proxy-Authorization`` on the HTTPS CONNECT
tunnel — which ``urllib`` does not send (hence the original ``407`` bug) — and
(b) intercepts TLS, presenting a leaf chaining to its own published CA. The fix
fetches with ``requests`` and validates the tunnel against the committed Bright
Data CA + the system roots, with verification kept ON.

These tests exercise the transport WITHOUT live Bright Data by monkeypatching the
``requests.Session`` the module builds, so they assert real behavior (status,
headers, body, error surfacing, the exact username format, and the TLS context
settings) deterministically and offline. The live residential capture is proven
separately by running the actual ``same_second_batch`` against creds.
"""

from __future__ import annotations

import ssl
import threading
from datetime import UTC, datetime

import pytest
import requests

from amber.capture import brightdata
from amber.capture.credentials import BrightDataCredentials
from amber.capture.record import CaptureRecord

CREDS = BrightDataCredentials(
    mode="proxy",
    customer_id="hl_test",
    zone="residential_proxy1",
    password="zone-pass",
)
URL = "https://shop.example/product/amber-hero-001"


# --------------------------------------------------------------------------- #
# A fake requests.Session that records calls and returns a canned response.
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str], content: bytes) -> None:
        self.status_code = status_code
        self.headers = headers
        self.content = content


class _FakeSession:
    """Stands in for requests.Session: records mounts/proxies, returns canned data."""

    def __init__(self, *, response=None, exc=None) -> None:
        self._response = response
        self._exc = exc
        self.proxies: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.mounts: dict[str, object] = {}
        self.get_calls: list[tuple[str, dict]] = []
        self.closed = False

    def mount(self, prefix: str, adapter: object) -> None:
        self.mounts[prefix] = adapter

    def get(self, url: str, **kwargs):
        self.get_calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        return self._response

    def close(self) -> None:
        self.closed = True


def _patch_session(monkeypatch, *, response=None, exc=None) -> dict[str, _FakeSession]:
    """Patch requests.Session so the module builds our fake; return a capture box."""
    box: dict[str, _FakeSession] = {}

    def factory():
        fake = _FakeSession(response=response, exc=exc)
        box["session"] = fake
        return fake

    monkeypatch.setattr(brightdata.requests, "Session", factory)
    return box


# --------------------------------------------------------------------------- #
# Username + session-token format (the proven-correct contract).
# --------------------------------------------------------------------------- #
def test_proxy_username_exact_format_per_country_and_session():
    user = brightdata._proxy_username(CREDS, "DE", "abc123")
    assert user == "brd-customer-hl_test-zone-residential_proxy1-country-de-session-abc123"


def test_proxy_username_lowercases_country():
    user = brightdata._proxy_username(CREDS, "BE", "sess9")
    assert "-country-be-session-sess9" in user


def test_session_token_hyphens_stripped_to_avoid_407():
    """A hyphen inside the session token corrupts BD's username parser (407);
    the on-wire token must be alphanumeric. The batch builds hyphenated labels
    like ``amber-de-1-1748…`` — those MUST be sanitized."""
    assert brightdata._sanitize_session_token("amber-de-1-1748000000000") == "amberde11748000000000"
    user = brightdata._proxy_username(CREDS, "DE", "amber-de-1-1748000000000")
    assert user.endswith("-session-amberde11748000000000")
    assert "amber-de-1" not in user  # no stray hyphen segments


def test_session_token_sanitization_is_distinct_per_label():
    """Distinct labels must yield distinct tokens (the within-country control)."""
    a = brightdata._sanitize_session_token("amber-de-1-1700000000001")
    b = brightdata._sanitize_session_token("amber-de-2-1700000000002")
    assert a != b


def test_session_token_with_no_alphanumerics_is_surfaced():
    with pytest.raises(brightdata.CaptureError):
        brightdata._sanitize_session_token("---")


# --------------------------------------------------------------------------- #
# Proxy session construction: proxies, headers, TLS adapter.
# --------------------------------------------------------------------------- #
def test_build_proxy_session_sets_proxies_headers_and_tls_adapter(monkeypatch):
    box = _patch_session(monkeypatch)
    sess = brightdata._build_proxy_session(CREDS, "DE", "abc123")
    fake = box["session"]
    expected_user = "brd-customer-hl_test-zone-residential_proxy1-country-de-session-abc123"
    expected_proxy = f"http://{expected_user}:zone-pass@brd.superproxy.io:33335"
    assert fake.proxies == {"http": expected_proxy, "https": expected_proxy}
    assert fake.headers["User-Agent"].startswith("Mozilla/5.0")
    # Both schemes get the BD TLS adapter (validates the intercepted tunnel).
    assert isinstance(fake.mounts["https://"], brightdata._BrightDataTLSAdapter)
    assert isinstance(fake.mounts["http://"], brightdata._BrightDataTLSAdapter)
    assert sess is fake


def test_tls_adapter_keeps_verification_on_and_relaxes_only_strict_flag():
    """The TLS context must keep hostname checking + CERT_REQUIRED (verification
    stays ON) and trust the committed BD CA; only VERIFY_X509_STRICT is cleared."""
    adapter = brightdata._BrightDataTLSAdapter(brightdata._brightdata_ca_data())
    ctx = adapter._build_context()
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert not (ctx.verify_flags & ssl.VERIFY_X509_STRICT)
    # The committed BD CA is loaded into the trust store.
    subjects = [c.get("subject") for c in ctx.get_ca_certs()]
    flat = [item for subj in subjects for rdn in subj for item in rdn]
    assert ("commonName", "Bright Data Proxy Root CA") in flat


def test_committed_ca_is_a_brightdata_root():
    pem = brightdata._brightdata_ca_data()
    assert "BEGIN CERTIFICATE" in pem
    from cryptography import x509

    cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
    assert "Bright Data" in cert.subject.rfc4514_string()


# --------------------------------------------------------------------------- #
# Fetch behavior: success, capturable error status, transport failure.
# --------------------------------------------------------------------------- #
def test_fetch_via_proxy_captures_status_headers_body(monkeypatch):
    resp = _FakeResponse(
        200,
        {"Content-Type": "application/json", "X-Currency": "EUR"},
        b'{"price":"129.99"}',
    )
    _patch_session(monkeypatch, response=resp)
    sess = brightdata._build_proxy_session(CREDS, "DE", "s1")
    res = brightdata._fetch_via_proxy(sess, URL, 30)
    assert res.status == 200
    assert res.body == b'{"price":"129.99"}'
    # Headers are lower-cased (the shape the floor/record expect).
    assert res.headers["content-type"] == "application/json"
    assert res.headers["x-currency"] == "EUR"


def test_fetch_via_proxy_http_error_status_is_a_capturable_result(monkeypatch):
    """A 451/403 is a REAL capturable result — body+headers+status kept, NOT raised
    (the floor classifies it as a possible geo/access block)."""
    for status in (403, 451, 503):
        resp = _FakeResponse(
            status,
            {"Content-Type": "text/html", "Retry-After": "60"},
            b"<html>blocked in your region</html>",
        )
        _patch_session(monkeypatch, response=resp)
        sess = brightdata._build_proxy_session(CREDS, "DE", "s1")
        res = brightdata._fetch_via_proxy(sess, URL, 30)
        assert res.status == status
        assert res.body == b"<html>blocked in your region</html>"
        assert res.headers["retry-after"] == "60"


def test_fetch_via_proxy_transport_failure_raises_capture_error(monkeypatch):
    """A genuine transport failure (proxy 407, DNS, timeout, TLS) must surface as
    CaptureError — never silently swallowed, never a fabricated record."""
    _patch_session(
        monkeypatch,
        exc=requests.exceptions.ProxyError("Tunnel connection failed: 407 Invalid Auth"),
    )
    sess = brightdata._build_proxy_session(CREDS, "DE", "s1")
    with pytest.raises(brightdata.CaptureError) as ei:
        brightdata._fetch_via_proxy(sess, URL, 30)
    assert "proxy fetch failed" in str(ei.value)


def test_fetch_via_proxy_timeout_raises_capture_error(monkeypatch):
    _patch_session(monkeypatch, exc=requests.exceptions.Timeout("read timed out"))
    sess = brightdata._build_proxy_session(CREDS, "DE", "s1")
    with pytest.raises(brightdata.CaptureError):
        brightdata._fetch_via_proxy(sess, URL, 1)


# --------------------------------------------------------------------------- #
# Exit-IP / country discovery via the BD welcome echo (offline, mocked).
# --------------------------------------------------------------------------- #
def test_discover_exit_ip_parses_welcome_echo(monkeypatch):
    welcome = b"Welcome to Bright Data\nCountry: de\nYour IP: 91.10.20.30\n"
    _patch_session(monkeypatch, response=_FakeResponse(200, {}, welcome))
    sess = brightdata._build_proxy_session(CREDS, "DE", "s1")
    assert brightdata._discover_exit_ip(sess, 30) == "91.10.20.30"


def test_exit_country_from_echo_parses_country(monkeypatch):
    welcome = b"Country: be\nYour IP: 78.21.1.2\n"
    _patch_session(monkeypatch, response=_FakeResponse(200, {}, welcome))
    sess = brightdata._build_proxy_session(CREDS, "BE", "s1")
    assert brightdata._exit_country_from_echo(sess, 30) == "BE"


def test_discover_exit_ip_falls_back_to_json_echo(monkeypatch):
    """If the welcome echo lacks an IP line, fall back to the JSON IP echo."""
    calls = {"n": 0}

    class _Box:
        proxies: dict = {}
        headers: dict = {}

        def mount(self, *_a):
            pass

        def get(self, _url, **_kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return _FakeResponse(200, {}, b"no ip here\n")  # welcome, no IP line
            return _FakeResponse(200, {}, b'{"ip":"203.0.113.9"}')  # JSON fallback

        def close(self):
            pass

    monkeypatch.setattr(brightdata.requests, "Session", _Box)
    sess = brightdata._build_proxy_session(CREDS, "DE", "s1")
    assert brightdata._discover_exit_ip(sess, 30) == "203.0.113.9"


def test_discover_exit_ip_unresolvable_raises(monkeypatch):
    """Both echoes failing to yield an IP must raise — an unattributable capture
    undermines the geo claim, so we never guess."""

    class _Box:
        proxies: dict = {}
        headers: dict = {}

        def mount(self, *_a):
            pass

        def get(self, _url, **_kw):
            return _FakeResponse(200, {}, b"no ip\n")  # neither welcome nor JSON has an IP

        def close(self):
            pass

    monkeypatch.setattr(brightdata.requests, "Session", _Box)
    sess = brightdata._build_proxy_session(CREDS, "DE", "s1")
    with pytest.raises(brightdata.CaptureError):
        brightdata._discover_exit_ip(sess, 30)


# --------------------------------------------------------------------------- #
# capture_one (proxy mode), fully mocked, closes the session.
# --------------------------------------------------------------------------- #
def test_capture_one_proxy_mode_builds_record_and_closes_session(monkeypatch):
    """capture_one runs discover-IP -> echo-country -> fetch on one session and
    returns a record carrying the real exit metadata; the session is closed."""
    sessions_made: list[_FakeSession] = []

    welcome = b"Country: de\nYour IP: 91.10.20.30\n"
    product = b'{"sku":"AMBER-HERO-001","price":"129.99","currency":"EUR"}'

    class _Seq(_FakeSession):
        def get(self, url, **kwargs):
            self.get_calls.append((url, kwargs))
            if "welcome.txt" in url:
                return _FakeResponse(200, {}, welcome)
            return _FakeResponse(200, {"Content-Type": "application/json"}, product)

    def factory():
        s = _Seq()
        sessions_made.append(s)
        return s

    monkeypatch.setattr(brightdata.requests, "Session", factory)

    rec, fetched_at = brightdata.capture_one(
        CREDS, URL, "DE", "amber-de-1-1748000000000", "de-01", timeout=30
    )
    assert rec.http_status == 200
    assert rec.exit_ip == "91.10.20.30"
    assert rec.proxy_reported_country == "DE"
    assert rec.requested_country == "DE"
    assert rec.session_id == "amber-de-1-1748000000000"  # human label preserved
    assert rec.body == product
    assert rec.headers["content-type"] == "application/json"
    assert fetched_at is not None
    # capture_one stamps the real dispatch instant (full ms precision, ...Z).
    assert rec.dispatched_at.endswith("Z") and "T" in rec.dispatched_at
    brightdata._parse_iso_instant(rec.dispatched_at)  # parses cleanly
    # The session was opened and closed (no leaked connections).
    assert sessions_made and sessions_made[0].closed is True


# --------------------------------------------------------------------------- #
# Concurrent batch dispatch (FIX 1): all captures launched concurrently, distinct
# sticky sessions preserved, capture_id ordering stable, failures surfaced.
# These mock capture_one (no network) to assert the batch's concurrency + wiring.
# --------------------------------------------------------------------------- #
def test_batch_dispatches_all_captures_concurrently(monkeypatch):
    """The batch must DISPATCH every capture concurrently (threads), so the launch
    instants cluster within a second even when each fetch then takes time. We
    prove concurrency with a barrier: each fake capture_one blocks until all N
    have STARTED — only possible if they run on distinct threads simultaneously."""
    n_total = 6  # DE x3 + BE x3
    barrier = threading.Barrier(n_total, timeout=10)
    seen_sessions: list[str] = []
    seen_threads: set[int] = set()
    lock = threading.Lock()

    def fake_capture_one(creds, url, country, session, capture_id, *, timeout):
        with lock:
            seen_sessions.append(session)
            seen_threads.add(threading.get_ident())
        # Block until ALL captures have entered: deadlocks (and times out) unless
        # they were dispatched concurrently.
        barrier.wait()
        # Stamp AFTER the barrier so all dispatched_at values are within
        # microseconds of each other — the spread is then deterministically
        # well under 1 s regardless of OS scheduling delays before the barrier.
        dispatched = datetime.now(UTC)
        rec = CaptureRecord(
            capture_id=capture_id,
            url=url,
            requested_country=country.upper(),
            session_id=session,
            exit_ip=f"203.0.113.{len(seen_sessions)}",
            requested_at=brightdata._iso_second(dispatched),
            http_status=200,
            headers={"content-type": "application/json"},
            body=b'{"price":"129.99","currency":"EUR"}',
            dispatched_at=brightdata._iso_instant(dispatched),
        )
        return rec, dispatched

    monkeypatch.setattr(brightdata, "capture_one", fake_capture_one)

    records = brightdata.same_second_batch_per_country_url(
        CREDS,
        {"DE": "https://shop.de/p", "BE": "https://shop.be/p"},
        3,
    )

    assert len(records) == n_total
    # Distinct sticky sessions (the within-country control): N distinct tokens.
    assert len({r.session_id for r in records}) == n_total
    # Captures ran on multiple threads (truly concurrent dispatch, not a loop).
    assert len(seen_threads) > 1
    # Deterministic capture_id ordering, independent of completion order.
    assert [r.capture_id for r in records] == [
        "de-01",
        "de-02",
        "de-03",
        "be-01",
        "be-02",
        "be-03",
    ]
    # Every record carries a dispatch stamp and the batch is dispatched-same-second
    # (the concurrent launches clustered well within a second).
    assert all(r.dispatched_at for r in records)
    assert brightdata.dispatched_same_second(records) is True


def test_batch_surfaces_a_worker_failure_naming_country_and_session(monkeypatch):
    """A failure in ANY concurrent worker must propagate as a CaptureError naming
    the failing country + session — never a silent or partial batch."""

    def fake_capture_one(creds, url, country, session, capture_id, *, timeout):
        if capture_id == "be-02":
            raise brightdata.CaptureError("proxy fetch failed: simulated")
        dispatched = datetime.now(UTC)
        rec = CaptureRecord(
            capture_id=capture_id,
            url=url,
            requested_country=country.upper(),
            session_id=session,
            exit_ip="203.0.113.1",
            requested_at=brightdata._iso_second(dispatched),
            http_status=200,
            headers={},
            body=b"{}",
            dispatched_at=brightdata._iso_instant(dispatched),
        )
        return rec, dispatched

    monkeypatch.setattr(brightdata, "capture_one", fake_capture_one)

    with pytest.raises(brightdata.CaptureError) as ei:
        brightdata.same_second_batch_per_country_url(
            CREDS, {"DE": "https://shop.de/p", "BE": "https://shop.be/p"}, 2
        )
    msg = str(ei.value)
    assert "BE" in msg and "be-02" in msg


def test_batch_rejects_zero_sessions(monkeypatch):
    monkeypatch.setattr(brightdata, "capture_one", lambda *a, **k: None)
    with pytest.raises(brightdata.CaptureError):
        brightdata.same_second_batch_per_country_url(CREDS, {"DE": "https://shop.de/p"}, 0)


def test_batch_distinct_sessions_with_a_frozen_clock(monkeypatch):
    """Session-token distinctness within a batch must come from the (country,index)
    pair, NOT the wall clock: with the per-batch millisecond stamp frozen, the 3
    DE exits must still get 3 distinct sticky tokens (the within-country control)."""

    def fake_capture_one(creds, url, country, session, capture_id, *, timeout):
        dispatched = datetime.now(UTC)
        rec = CaptureRecord(
            capture_id=capture_id,
            url=url,
            requested_country=country.upper(),
            session_id=session,
            exit_ip="203.0.113.1",
            requested_at=brightdata._iso_second(dispatched),
            http_status=200,
            headers={},
            body=b"{}",
            dispatched_at=brightdata._iso_instant(dispatched),
        )
        return rec, dispatched

    # Freeze the per-batch stamp so distinctness cannot rely on it.
    monkeypatch.setattr(brightdata.time, "time", lambda: 1748000000.0)
    monkeypatch.setattr(brightdata, "capture_one", fake_capture_one)

    records = brightdata.same_second_batch_per_country_url(
        CREDS, {"DE": "https://shop.de/p"}, 3
    )
    assert len({r.session_id for r in records}) == 3


# --------------------------------------------------------------------------- #
# Classified-retry integration (the PR #155 port). The retry wraps ONLY the
# THROWN transport-failure path; a returned TARGET status is a capturable result
# and is never retried; retries stay on the SAME sticky session (same exit).
# All injected: no real sleeping, deterministic jitter, no live Bright Data.
# --------------------------------------------------------------------------- #
class _SequencedSession:
    """A fake session whose product fetch yields a SCRIPTED sequence of outcomes.

    Each ``get`` of the product URL pops the next item: a ``_FakeResponse`` is
    returned (a real captured result), an ``Exception`` instance is raised (a
    thrown transport failure). The welcome/IP echo always succeeds so the retry
    is exercised on the PRODUCT fetch specifically. ``product_get_count`` records
    how many times the product URL was fetched (the attempt count).
    """

    def __init__(self, product_sequence: list) -> None:
        self._seq = list(product_sequence)
        self.proxies: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.product_get_count = 0
        self.closed = False

    def mount(self, *_a) -> None:
        pass

    def get(self, url: str, **_kw):
        if "welcome.txt" in url or "ipify" in url:
            return _FakeResponse(200, {}, b"Country: de\nYour IP: 91.10.20.30\n")
        self.product_get_count += 1
        item = self._seq.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self) -> None:
        self.closed = True


def _patch_no_sleep(monkeypatch) -> list[float]:
    """Patch the transport sleep so retries do not actually wait; record the
    delays so the test can assert backoff was applied. Also pin rng to a fixed
    value for deterministic jitter."""
    slept: list[float] = []
    monkeypatch.setattr(brightdata.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(brightdata.random, "random", lambda: 0.5)
    return slept


def test_capture_one_retries_transient_transport_error_then_succeeds(monkeypatch):
    """A transient transport blip on the product fetch (a reset) is retried on the
    SAME session and then succeeds: one record, never a failed batch."""
    slept = _patch_no_sleep(monkeypatch)
    product = b'{"sku":"AMBER-HERO-001","price":"129.99","currency":"EUR"}'
    sessions: list[_SequencedSession] = []

    # requests wraps a socket reset into requests.exceptions.ConnectionError with
    # the OSError chained as __cause__ (exactly what _fetch_via_proxy then wraps
    # into CaptureError). Reproduce that realistic shape so the test exercises the
    # production classification path (the chained errno is what marks it transient).
    reset = requests.exceptions.ConnectionError("Connection aborted")
    reset.__cause__ = ConnectionResetError(104, "Connection reset by peer")

    def factory():
        s = _SequencedSession(
            [
                reset,  # 1st product fetch: a transient reset
                _FakeResponse(200, {"Content-Type": "application/json"}, product),  # retry ok
            ]
        )
        sessions.append(s)
        return s

    monkeypatch.setattr(brightdata.requests, "Session", factory)
    rec, _fetched = brightdata.capture_one(
        CREDS, URL, "DE", "amber-de-1-1748000000000", "de-01", timeout=30
    )
    assert rec.http_status == 200
    assert rec.body == product
    # Exactly one retry happened (2 product fetches), on the SAME session object.
    assert len(sessions) == 1
    assert sessions[0].product_get_count == 2
    assert len(slept) == 1 and slept[0] >= 0  # one backoff sleep, non-negative


def test_capture_one_persistent_transient_error_retries_then_raises(monkeypatch):
    """A persistently-failing transient transport error is retried EXACTLY
    max_retries times (default 2 -> 3 product attempts) then raises CaptureError."""
    slept = _patch_no_sleep(monkeypatch)
    sessions: list[_SequencedSession] = []

    def factory():
        s = _SequencedSession(
            [
                requests.exceptions.ConnectionError("reset 1"),
                requests.exceptions.ConnectionError("reset 2"),
                requests.exceptions.ConnectionError("reset 3"),
                requests.exceptions.ConnectionError("reset 4"),  # never reached
            ]
        )
        sessions.append(s)
        return s

    monkeypatch.setattr(brightdata.requests, "Session", factory)
    with pytest.raises(brightdata.CaptureError):
        brightdata.capture_one(CREDS, URL, "DE", "s1", "de-01", timeout=30)
    # Default budget = 2 retries -> 3 product attempts total, then give up.
    assert sessions[0].product_get_count == 3
    assert len(slept) == 2  # two backoff waits between the three attempts


def test_capture_one_returned_target_status_is_not_retried(monkeypatch):
    """A returned TARGET 4xx/5xx is a capturable result: returned on the FIRST
    fetch, never retried (the forensic guard). One product fetch, status kept."""
    slept = _patch_no_sleep(monkeypatch)
    sessions: list[_SequencedSession] = []
    blocked = b"<html>unavailable for legal reasons</html>"

    def factory():
        s = _SequencedSession(
            [_FakeResponse(451, {"Content-Type": "text/html"}, blocked)]
        )
        sessions.append(s)
        return s

    monkeypatch.setattr(brightdata.requests, "Session", factory)
    rec, _fetched = brightdata.capture_one(CREDS, URL, "DE", "s1", "de-01", timeout=30)
    assert rec.http_status == 451  # the target status is the captured result
    assert rec.body == blocked
    assert sessions[0].product_get_count == 1  # NOT retried
    assert slept == []  # no backoff for a captured result


def test_capture_one_terminal_transport_error_is_not_retried(monkeypatch):
    """An UNRECOGNIZED (terminal) transport failure is surfaced at once, never
    burning the retry budget on a hopeless retry."""
    slept = _patch_no_sleep(monkeypatch)
    sessions: list[_SequencedSession] = []

    class _WeirdTransport(requests.exceptions.RequestException):
        pass

    def factory():
        s = _SequencedSession([_WeirdTransport("unclassifiable")])
        sessions.append(s)
        return s

    monkeypatch.setattr(brightdata.requests, "Session", factory)
    with pytest.raises(brightdata.CaptureError):
        brightdata.capture_one(CREDS, URL, "DE", "s1", "de-01", timeout=30)
    assert sessions[0].product_get_count == 1  # tried once, no retry
    assert slept == []


def test_retry_budget_is_env_tunable(monkeypatch):
    """AMBER_CAPTURE_MAX_RETRIES raises the budget; a malformed value falls back
    to the default. The knob is read live so an operator can tune resilience."""
    monkeypatch.setenv("AMBER_CAPTURE_MAX_RETRIES", "4")
    assert brightdata._capture_max_retries() == 4
    monkeypatch.setenv("AMBER_CAPTURE_MAX_RETRIES", "garbage")
    assert brightdata._capture_max_retries() == brightdata.DEFAULT_CAPTURE_MAX_RETRIES
    monkeypatch.setenv("AMBER_CAPTURE_MAX_RETRIES", "-1")  # negative -> default
    assert brightdata._capture_max_retries() == brightdata.DEFAULT_CAPTURE_MAX_RETRIES
    monkeypatch.delenv("AMBER_CAPTURE_MAX_RETRIES", raising=False)
    assert brightdata._capture_max_retries() == 2  # documented default


def test_backoff_knobs_are_env_tunable(monkeypatch):
    monkeypatch.setenv("AMBER_CAPTURE_BASE_BACKOFF_MS", "250")
    monkeypatch.setenv("AMBER_CAPTURE_MAX_BACKOFF_MS", "5000")
    opts = brightdata._capture_backoff_opts()
    assert opts.base_ms == 250.0
    assert opts.max_ms == 5000.0
    assert opts.jitter == "full"
    # Malformed -> defaults (no crash, no negative backoff).
    monkeypatch.setenv("AMBER_CAPTURE_BASE_BACKOFF_MS", "nope")
    monkeypatch.setenv("AMBER_CAPTURE_MAX_BACKOFF_MS", "-9")
    opts2 = brightdata._capture_backoff_opts()
    assert opts2.base_ms == brightdata.DEFAULT_CAPTURE_BASE_BACKOFF_MS
    assert opts2.max_ms == brightdata.DEFAULT_CAPTURE_MAX_BACKOFF_MS


def test_with_transport_retry_honors_retry_after_capped(monkeypatch):
    """A transient failure that classifies with a server Retry-After waits that
    value (clamped to max). We drive _with_transport_retry directly with an
    injected sleep + a classification carrying retry_after_ms, proving the
    server value wins over the computed band and is capped at max_ms."""
    slept: list[float] = []
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            exc = brightdata.CaptureError("transient")
            exc.__cause__ = requests.exceptions.ConnectionError("reset")
            raise exc
        return "ok"

    # Force the classification to carry a huge Retry-After so we see the cap.
    def fake_classify(_cause):
        return brightdata._retry.Classification(
            brightdata._retry.OUTCOME_RATE_LIMITED, 429, 120000, True, "rate limited"
        )

    monkeypatch.setattr(brightdata._retry, "classify_transport_error", fake_classify)
    out = brightdata._with_transport_retry(
        fetch,
        max_retries=2,
        opts=brightdata._retry.BackoffOpts(max_ms=30000, jitter="none"),
        sleep=lambda s: slept.append(s),
        rng=lambda: 0.5,
    )
    assert out == "ok"
    # 120000ms Retry-After clamped to 30000ms max -> a 30.0s wait.
    assert slept == [30.0]
