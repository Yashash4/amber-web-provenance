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

import pytest
import requests

from amber.capture import brightdata
from amber.capture.credentials import BrightDataCredentials

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
    # The session was opened and closed (no leaked connections).
    assert sessions_made and sessions_made[0].closed is True
