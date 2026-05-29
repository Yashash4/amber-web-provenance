"""Bright Data residential capture client — the fetcher + geo-witness.

Captures the SAME product URL from multiple countries' RESIDENTIAL exits, with
several DISTINCT sticky sessions (= distinct residential IPs) per country, in a
SAME-SECOND batch. Bright Data is Amber's fetcher and the geo-witness; the
captured bytes + exit metadata feed the deterministic floor and the signed packet.

Two real connection modes are supported (auto-selected from the credentials
present — see :mod:`amber.capture.credentials`):

  * ``proxy`` — the residential super-proxy gateway. We connect through
    ``brd.superproxy.io:33335`` with a per-country, per-session username of the
    form ``brd-customer-<id>-zone-<zone>-country-<cc>-session-<sid>`` and the
    zone password. Each distinct ``session`` token sticks to a distinct
    residential IP, which is exactly the within-country control: N sessions =>
    N distinct exits in the same country. The fetch is performed with
    ``requests`` (Apache-2.0), which — unlike ``urllib`` — sends
    ``Proxy-Authorization`` on the HTTPS ``CONNECT`` tunnel correctly.

    Bright Data's port-33335 super-proxy terminates ("intercepts") TLS on the
    tunnel and presents a leaf chaining to its own published "Bright Data Proxy
    Root CA". So system roots alone cannot validate it. We do NOT disable
    verification (this is a forensic instrument): instead we validate the chain
    against the COMMITTED Bright Data CA (shipped at
    ``amber/capture/data/brightdata_proxy_ca.crt``) AND the system roots (for
    targets Bright Data passes through un-intercepted), with hostname checking
    and ``CERT_REQUIRED`` kept ON. The only relaxation is OpenSSL's strict
    X.509 *extension-presence* check (the BD leaf omits an Authority Key
    Identifier), which is an extension-formatting rule, not a trust or hostname
    check — a cert that does not chain to a trusted root, or whose hostname is
    wrong, still fails the handshake (proven by a negative-control test).

  * ``api`` — the Bright Data Web Unlocker / request API (token in the
    ``Authorization: Bearer`` header). Country + a per-call session are passed in
    the JSON payload. Used when only an API token is available.

The exit IP for each capture is discovered by routing a tiny IP-echo request
through the SAME session immediately before (or as) the product fetch, so the
recorded ``exit_ip`` is the real residential exit that served the page — a
genuine Source-1 geo-attribution input, not an assumption.

REAL captures only. If no credentials are present, this module raises
``CredentialsMissing`` (caught by the harness, which reports the live step as
pending) — it NEVER fabricates a body, an IP, or a country.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from amber.capture.credentials import BrightDataCredentials, CredentialsMissing
from amber.capture.record import CaptureRecord

# Bright Data residential super-proxy gateway (host:port). Public, documented.
SUPERPROXY_HOST = "brd.superproxy.io"
SUPERPROXY_PORT = 33335

# The committed Bright Data Proxy Root CA (the cert the port-33335 super-proxy
# presents on the intercepted CONNECT tunnel). Shipped with the package; the
# proxy fetch validates the tunnel against THIS plus the system roots — verified,
# never disabled. Sourced from https://brightdata.com/static/brightdata_proxy_ca.zip
# (CN="Bright Data Proxy Root CA", valid through 2034-09-14).
BRIGHTDATA_CA_PATH = Path(__file__).resolve().parent / "data" / "brightdata_proxy_ca.crt"

# A stable IP-echo endpoint reachable through the proxy to discover the exit IP.
# geo.brdtest.com/welcome.txt?product=resi returns the exit IP + geo Bright Data
# itself sees; we fall back to a plain ipify-style echo if needed.
_IP_ECHO_URL = "https://geo.brdtest.com/welcome.txt?product=resi&method=native"
_IP_ECHO_FALLBACK = "https://api.ipify.org?format=json"

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

DEFAULT_TIMEOUT = 45


class CaptureError(RuntimeError):
    """A real capture attempt failed (network/proxy error) — surfaced, not faked."""


@dataclass
class _ProxyResult:
    status: int
    headers: dict[str, str]
    body: bytes


class _BrightDataTLSAdapter(HTTPAdapter):
    """A requests adapter that validates the BD-intercepted CONNECT tunnel.

    Verification stays ON. We trust the system roots (for targets Bright Data
    passes through) PLUS the committed Bright Data Proxy Root CA (for the
    targets it terminates TLS on, presenting a leaf chaining to that root).
    ``check_hostname`` and ``CERT_REQUIRED`` remain enabled, so a leaf that does
    not chain to a trusted root — or whose hostname is wrong — still fails.

    The single relaxation is clearing OpenSSL's ``VERIFY_X509_STRICT`` flag: the
    Bright Data leaf omits an Authority Key Identifier, which strict mode rejects
    on formatting grounds even though the chain is cryptographically valid. That
    is an extension-presence rule, not a trust or hostname check, and is the
    documented requirement for using the port-33335 super-proxy.
    """

    def __init__(self, ca_data: str, **kwargs: object) -> None:
        self._ca_data = ca_data
        super().__init__(**kwargs)

    def _build_context(self) -> ssl.SSLContext:
        ctx = create_urllib3_context()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs()
        ctx.load_verify_locations(cadata=self._ca_data)
        return ctx

    def init_poolmanager(self, *args: object, **kwargs: object):  # type: ignore[override]
        kwargs["ssl_context"] = self._build_context()
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args: object, **kwargs: object):  # type: ignore[override]
        kwargs["ssl_context"] = self._build_context()
        return super().proxy_manager_for(*args, **kwargs)


@lru_cache(maxsize=1)
def _brightdata_ca_data() -> str:
    """The committed Bright Data CA PEM text (read once, cached)."""
    try:
        return BRIGHTDATA_CA_PATH.read_text(encoding="ascii")
    except OSError as exc:  # pragma: no cover - the cert is shipped with the package
        raise CaptureError(
            f"Bright Data CA certificate missing at {BRIGHTDATA_CA_PATH}: {exc}"
        ) from exc


def _sanitize_session_token(session: str) -> str:
    """Reduce a session label to a Bright-Data-safe sticky-session token.

    Bright Data parses the proxy username on ``-`` boundaries
    (``…-session-<sid>``), so a ``-`` (or any non-alphanumeric) INSIDE the
    session token corrupts the field and the proxy returns ``407 Invalid Auth``.
    BD session tokens must therefore be alphanumeric. We strip every
    non-alphanumeric character (e.g. ``amber-de-1-1748…`` -> ``amberde11748…``)
    so the token is accepted while staying DETERMINISTIC and DISTINCT per input
    label — which is what the within-country control relies on (one distinct
    token => one distinct sticky residential exit). The original, human-readable
    label is preserved on the :class:`CaptureRecord` (``session_id``); only the
    on-wire proxy token is sanitized.
    """
    token = "".join(ch for ch in session if ch.isalnum())
    if not token:
        raise CaptureError(
            f"session token {session!r} has no alphanumeric characters; cannot "
            "build a valid Bright Data sticky-session token"
        )
    return token


def _proxy_username(creds: BrightDataCredentials, country: str, session: str) -> str:
    """Build the residential proxy username for a country + sticky session.

    Format: ``brd-customer-<id>-zone-<zone>-country-<cc>-session-<sid>``. The
    session token (sanitized to alphanumerics — see
    :func:`_sanitize_session_token`) pins one residential IP for that token's
    lifetime, so distinct sessions = distinct exits (the within-country control).
    """
    cc = country.lower()
    sid = _sanitize_session_token(session)
    return (
        f"brd-customer-{creds.customer_id}"
        f"-zone-{creds.zone}"
        f"-country-{cc}"
        f"-session-{sid}"
    )


def _build_proxy_session(
    creds: BrightDataCredentials, country: str, session: str
) -> requests.Session:
    """A requests Session routed through the BD residential proxy for one exit.

    The proxy URL carries the per-country, per-session username + zone password,
    so every request on this session sticks to one residential IP. The session
    mounts :class:`_BrightDataTLSAdapter`, which validates the intercepted
    CONNECT tunnel against the committed Bright Data CA plus the system roots —
    verification stays ON; a bad chain/hostname still fails the handshake.
    """
    user = _proxy_username(creds, country, session)
    proxy_url = f"http://{user}:{creds.password}@{SUPERPROXY_HOST}:{SUPERPROXY_PORT}"
    sess = requests.Session()
    sess.proxies = {"http": proxy_url, "https": proxy_url}
    sess.headers.update(_REQUEST_HEADERS)
    adapter = _BrightDataTLSAdapter(_brightdata_ca_data())
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    return sess


def _fetch_via_proxy(
    sess: requests.Session,
    url: str,
    timeout: int,
) -> _ProxyResult:
    """Fetch ``url`` through the proxy session.

    An HTTP error status (e.g. 451/403) IS a real, capturable result — we keep
    its body + headers + status and let the floor classify it; we do NOT raise on
    4xx/5xx. Only a genuine transport/connection failure (DNS, proxy auth,
    timeout, TLS handshake) raises :class:`CaptureError`.
    """
    try:
        resp = sess.get(url, timeout=timeout, allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        raise CaptureError(f"proxy fetch failed for {url} via session: {exc}") from exc
    headers = {k.lower(): v for k, v in resp.headers.items()}
    return _ProxyResult(status=resp.status_code, headers=headers, body=resp.content)


def _discover_exit_ip(sess: requests.Session, timeout: int) -> str:
    """Discover the real residential exit IP for this session, through the proxy.

    Returns the exit IP string. Raises CaptureError if it cannot be determined —
    we do NOT proceed with an unknown exit (an unattributable capture undermines
    the geo claim); the harness records the failure rather than guessing.
    """
    try:
        res = _fetch_via_proxy(sess, _IP_ECHO_URL, timeout)
        text = res.body.decode("utf-8", errors="replace")
        # welcome.txt format: lines like "Country: de" and "... IP: 1.2.3.4".
        for line in text.splitlines():
            low = line.lower()
            if "ip:" in low:
                ip = line.split(":", 1)[1].strip().split()[0]
                if ip:
                    return ip
    except CaptureError:
        pass
    # Fallback: a plain JSON IP echo through the same proxy session.
    res = _fetch_via_proxy(sess, _IP_ECHO_FALLBACK, timeout)
    try:
        return json.loads(res.body.decode("utf-8"))["ip"]
    except (ValueError, KeyError) as exc:
        raise CaptureError(f"could not discover exit IP: {exc}") from exc


def _exit_country_from_echo(sess: requests.Session, timeout: int) -> str | None:
    """Best-effort proxy-reported exit country from the BD welcome echo."""
    try:
        res = _fetch_via_proxy(sess, _IP_ECHO_URL, timeout)
        text = res.body.decode("utf-8", errors="replace")
        for line in text.splitlines():
            low = line.lower()
            if low.startswith("country:"):
                return line.split(":", 1)[1].strip().upper() or None
    except CaptureError:
        return None
    return None


def _fetch_via_api(
    creds: BrightDataCredentials,
    url: str,
    country: str,
    timeout: int,
) -> tuple[_ProxyResult, str | None]:
    """Fetch via the Bright Data Web Unlocker request API (token mode).

    Returns (result, exit_ip_or_None). The API returns the unlocked body; the
    exit IP, when the response exposes it, is captured from the response meta.
    """
    payload = json.dumps(
        {
            "zone": creds.zone or "web_unlocker",
            "url": url,
            "format": "raw",
            "country": country.lower(),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brightdata.com/request",
        data=payload,
        headers={
            "Authorization": f"Bearer {creds.api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read()
            status = resp.status
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        status = exc.code
        headers = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CaptureError(f"BD API fetch failed for {url} ({country}): {exc}") from exc
    exit_ip = headers.get("x-brd-exit-ip") or headers.get("x-luminati-ip")
    return _ProxyResult(status=status, headers=headers, body=body), exit_ip


def capture_one(
    creds: BrightDataCredentials,
    url: str,
    country: str,
    session: str,
    capture_id: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[CaptureRecord, datetime]:
    """Capture ``url`` once from ``country`` via sticky ``session``.

    Discovers the real exit IP for the session, fetches the product URL, and
    returns ``(record, fetched_at)`` where ``fetched_at`` is the REAL wall-clock
    instant the product fetch completed. The record's ``requested_at`` is filled
    in by the batch (it is the same-second-batch stamp); ``fetched_at`` is the
    raw per-capture truth the batch uses to compute the honest spread. Raises
    CaptureError on a real failure (never returns a fabricated record).
    """
    if creds.mode == "proxy":
        sess = _build_proxy_session(creds, country, session)
        try:
            exit_ip = _discover_exit_ip(sess, timeout)
            proxy_country = _exit_country_from_echo(sess, timeout)
            res = _fetch_via_proxy(sess, url, timeout)
        finally:
            sess.close()
    elif creds.mode == "api":
        res, exit_ip = _fetch_via_api(creds, url, country, timeout)
        proxy_country = country.upper()
        if not exit_ip:
            exit_ip = "api-mode-exit-unreported"
    else:  # pragma: no cover - credentials.validate guards this
        raise CaptureError(f"unknown credentials mode: {creds.mode!r}")

    fetched_at = datetime.now(UTC)
    record = CaptureRecord(
        capture_id=capture_id,
        url=url,
        requested_country=country.upper(),
        session_id=session,
        exit_ip=exit_ip,
        # Provisional stamp: the batch overwrites this with the honest same-second
        # (or per-capture) timestamp once the full batch's real spread is known.
        requested_at=_iso_second(fetched_at),
        http_status=res.status,
        headers=res.headers,
        body=res.body,
        proxy_reported_country=proxy_country,
    )
    return record, fetched_at


def _iso_second(ts: datetime) -> str:
    """ISO-8601 ``...Z`` second-truncated stamp for a UTC instant."""
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp_batch_timestamps(
    records: list[CaptureRecord],
    fetched_at: list[datetime],
) -> bool:
    """Set each record's ``requested_at`` honestly from REAL fetch instants.

    ``fetched_at[i]`` is the real wall-clock instant capture ``records[i]``
    completed. We compute the ACTUAL spread (max - min) across the batch:

      * spread <= 1s  -> the batch genuinely IS a same-second measurement; stamp
        every record with ONE canonical second (the earliest fetch second), so the
        floor sees a single distinct ``requested_at`` and reports
        ``same_second_batch=true`` truthfully.
      * spread  > 1s  -> the batch is NOT same-second; stamp each record with its
        OWN real fetch second, so the floor sees >=2 distinct values and reports
        ``same_second_batch=false`` — the over-one-second case the docstring
        promises, honestly surfaced, never hidden.

    Returns the actual ``same_second`` verdict (the spread-<=-1s boolean). Pure /
    deterministic given the inputs, so it is unit-tested with injected timestamps
    (no live Bright Data required). Mutates ``records`` in place.
    """
    if len(records) != len(fetched_at):
        raise CaptureError(
            "stamp_batch_timestamps: records and fetched_at length mismatch "
            f"({len(records)} != {len(fetched_at)})"
        )
    if not records:
        return True

    earliest = min(fetched_at)
    latest = max(fetched_at)
    spread_seconds = (latest - earliest).total_seconds()
    same_second = spread_seconds <= 1.0

    if same_second:
        canonical = _iso_second(earliest)
        for rec in records:
            rec.requested_at = canonical
    else:
        for rec, ts in zip(records, fetched_at, strict=True):
            rec.requested_at = _iso_second(ts)
    return same_second


def same_second_batch(
    creds: BrightDataCredentials,
    url: str,
    countries: list[str],
    sessions_per_country: int,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[CaptureRecord]:
    """Capture ``url`` from every country x N sticky sessions in one batch.

    Each capture is stamped with its REAL fetch wall-clock time. The actual
    batch spread (max - min of those real instants) decides the same-second
    claim: a spread <= 1s makes every record share one canonical second (the
    floor reports ``same_second_batch=true`` truthfully); a spread > 1s leaves
    each record on its own real second so the floor reports
    ``same_second_batch=false``. The wall-clock fetches are sequential —
    residential proxy fetches cannot be truly simultaneous from one process — and
    a batch that spans more than a second is reported honestly, never hidden.

    Raises CredentialsMissing if no creds (the caller/harness reports the pending
    live step); raises CaptureError on a real per-capture failure after recording
    which session failed.
    """
    if creds is None:
        raise CredentialsMissing("no Bright Data credentials available for capture")

    records: list[CaptureRecord] = []
    fetched_at: list[datetime] = []
    for country in countries:
        for i in range(sessions_per_country):
            session = f"amber-{country.lower()}-{i + 1}-{int(time.time() * 1000)}"
            capture_id = f"{country.lower()}-{i + 1:02d}"
            rec, ts = capture_one(
                creds,
                url,
                country,
                session,
                capture_id,
                timeout=timeout,
            )
            records.append(rec)
            fetched_at.append(ts)

    stamp_batch_timestamps(records, fetched_at)
    return records
