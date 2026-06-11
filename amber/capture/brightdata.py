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

import hashlib
import json
import os
import random
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from amber.capture import retry as _retry
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

# SHA256 of the committed CA file (computed over the exact shipped bytes). The CA
# is loaded into the TLS trust store, so a substituted CA file would silently
# widen what the forensic instrument trusts. We PIN the hash and refuse to load a
# CA whose bytes do not match — a substituted/tampered CA fails closed (raise),
# never silently trusted. Re-pin deliberately (and review) if BD rotates the root.
BRIGHTDATA_CA_SHA256 = "db99f2797091440ae3da9751839736e468ed33eb2bdcac136b59be02237f929e"

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

# --------------------------------------------------------------------------- #
# Classified-retry policy for the capture transport (the Python port of the
# resilience policy Amber contributed upstream as PR #155). A multi-geo
# same-second batch dispatches N captures concurrently and reads each future's
# result, so the FIRST transient transport blip (a 502/504 from the super-proxy,
# a connection reset, a read timeout) would otherwise fail the whole batch. We
# retry ONLY a THROWN transport failure (never a returned target status, which is
# a capturable result), on the SAME sticky session (same residential exit, so the
# within-country control is preserved), with full-jitter exponential backoff.
#
# Defaults: 2 retries (3 attempts total). Small on purpose: captures want to ride
# out a transient blip, not to mask a genuinely dead exit or to inflate wall-clock
# time on a hopeless target. All three knobs are env-tunable (mirroring #155):
#   AMBER_CAPTURE_MAX_RETRIES     retries AFTER the first attempt (default 2)
#   AMBER_CAPTURE_BASE_BACKOFF_MS exponential base in ms                (default 500)
#   AMBER_CAPTURE_MAX_BACKOFF_MS  per-wait cap in ms                    (default 30000)
# A malformed/negative env value falls back to the default (never crashes, never
# a negative wait), matching the credentials/env style elsewhere in the package.
DEFAULT_CAPTURE_MAX_RETRIES = 2
DEFAULT_CAPTURE_BASE_BACKOFF_MS = 500.0
DEFAULT_CAPTURE_MAX_BACKOFF_MS = 30000.0

_T = TypeVar("_T")


class CaptureError(RuntimeError):
    """A real capture attempt failed (network/proxy error) — surfaced, not faked."""


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    """Read a non-negative int from the env, falling back to ``default``.

    A missing/blank/malformed/negative value yields ``default`` (no crash, no
    negative budget). Used for the retry-budget knob.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return val if val >= minimum else default


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    """Read a non-negative float from the env, falling back to ``default``.

    A missing/blank/malformed/negative value yields ``default`` (no crash, no
    negative backoff). Used for the backoff-ms knobs.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        return default
    return val if val >= minimum else default


def _capture_max_retries() -> int:
    """Retries AFTER the first attempt (env-tunable; default 2)."""
    return _env_int("AMBER_CAPTURE_MAX_RETRIES", DEFAULT_CAPTURE_MAX_RETRIES)


def _capture_backoff_opts() -> _retry.BackoffOpts:
    """The env-tunable full-jitter backoff policy for capture transport retries."""
    return _retry.BackoffOpts(
        base_ms=_env_float("AMBER_CAPTURE_BASE_BACKOFF_MS", DEFAULT_CAPTURE_BASE_BACKOFF_MS),
        max_ms=_env_float("AMBER_CAPTURE_MAX_BACKOFF_MS", DEFAULT_CAPTURE_MAX_BACKOFF_MS),
        factor=2.0,
        jitter="full",
    )


def _with_transport_retry(
    fetch: Callable[[], _T],
    *,
    max_retries: int | None = None,
    opts: _retry.BackoffOpts | None = None,
    sleep: Callable[[float], None] | None = None,
    rng: Callable[[], float] | None = None,
) -> _T:
    """Run ``fetch`` (a real transport call), retrying ONLY transient transport
    failures with full-jitter backoff before finally raising :class:`CaptureError`.

    ``fetch`` must perform the actual fetch and raise :class:`CaptureError` on a
    transport failure (as ``_fetch_via_proxy`` / ``_fetch_via_api`` already do),
    chaining the original ``requests`` / ``urllib`` exception as ``__cause__``. We
    classify that cause via :func:`amber.capture.retry.classify_transport_error`:
    a TRANSIENT failure (reset/timeout/refused/transient gateway blip) is retried
    on the SAME session object the caller closed over (same residential exit, so
    the within-country control is intact); a TERMINAL failure is re-raised at once
    (never burning the budget on a hopeless retry).

    A returned value (any HTTP status, including a target 4xx/5xx) flows straight
    through: it is a CAPTURABLE RESULT and is NEVER retried (the forensic guard:
    the returned status never raises, so it never reaches the except branch).
    ``sleep`` / ``rng`` are injected (resolved at call time off this module, so a
    test that monkeypatches ``brightdata.time.sleep`` / ``brightdata.random.random``
    is honored) for a loop that is unit-testable with no real waiting and
    deterministic jitter.
    """
    budget = _capture_max_retries() if max_retries is None else max_retries
    policy = opts or _capture_backoff_opts()
    do_sleep = sleep if sleep is not None else time.sleep
    do_rng = rng if rng is not None else random.random
    attempt = 0
    while True:
        try:
            return fetch()
        except CaptureError as exc:
            # Classify the ORIGINAL transport exception (chained as __cause__),
            # never the CaptureError wrapper itself. A returned target status is
            # not an exception, so it never reaches here (it is already returned).
            cause = exc.__cause__ if exc.__cause__ is not None else exc
            classification = _retry.classify_transport_error(cause)
            decision = _retry.should_retry(classification, attempt, budget, policy, do_rng)
            if not decision.retry:
                # Terminal, or budget exhausted: surface the real failure honestly.
                raise
            do_sleep(max(0.0, decision.delay_ms) / 1000.0)
            attempt += 1


@dataclass
class _ProxyResult:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class _CapturePlan:
    """One planned capture: its country, URL, distinct sticky session, and id."""

    country: str
    url: str
    session: str
    capture_id: str


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
    """The committed Bright Data CA PEM text (read once, cached, hash-pinned).

    The CA bytes are SHA256-verified against :data:`BRIGHTDATA_CA_SHA256` BEFORE
    they are trusted: the CA gets loaded into the TLS trust store, so silently
    accepting a substituted CA file would widen what this forensic instrument
    trusts. A hash mismatch fails CLOSED (raises) rather than trusting an
    unexpected root — the verification stays ON guarantee extends to the CA file
    itself, not just the handshake.
    """
    try:
        raw = BRIGHTDATA_CA_PATH.read_bytes()
    except OSError as exc:  # pragma: no cover - the cert is shipped with the package
        raise CaptureError(
            f"Bright Data CA certificate missing at {BRIGHTDATA_CA_PATH}: {exc}"
        ) from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != BRIGHTDATA_CA_SHA256:
        raise CaptureError(
            "Bright Data CA certificate hash mismatch: refusing to trust a CA whose "
            f"bytes do not match the pinned SHA256. expected {BRIGHTDATA_CA_SHA256}, "
            f"got {actual} (file {BRIGHTDATA_CA_PATH}). If Bright Data rotated the "
            "root, re-pin BRIGHTDATA_CA_SHA256 deliberately after verifying the new "
            "cert's provenance."
        )
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CaptureError(
            f"Bright Data CA certificate at {BRIGHTDATA_CA_PATH} is not ASCII PEM: {exc}"
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
    raw per-capture truth the batch uses to compute the honest spread.

    The record's ``dispatched_at`` is stamped HERE, at the real instant this
    capture is launched (before any network work) — so when the batch dispatches
    all captures concurrently, the dispatch instants cluster within a second even
    though each fetch then takes seconds. That is the honest simultaneity claim:
    DISPATCHED same second, not witnessed same second. Raises CaptureError on a
    real failure (never returns a fabricated record).
    """
    dispatched_at = datetime.now(UTC)
    if creds.mode == "proxy":
        sess = _build_proxy_session(creds, country, session)
        try:
            exit_ip = _discover_exit_ip(sess, timeout)
            proxy_country = _exit_country_from_echo(sess, timeout)
            # The product fetch is the load-bearing capture: ride out a transient
            # transport blip (502/504, reset, timeout) with the classified-retry
            # policy, on THIS SAME session (same residential exit, so the
            # within-country control holds). A returned target status (any 4xx/5xx)
            # is a capturable result and is returned unretried. dispatched_at was
            # already stamped above, BEFORE any retry, so the dispatched-same-second
            # verdict is unaffected; fetched_at below reflects the real completion.
            res = _with_transport_retry(lambda: _fetch_via_proxy(sess, url, timeout))
        finally:
            sess.close()
    elif creds.mode == "api":
        # Same resilience for API mode: a transient gateway failure is retried;
        # a returned status (the API surfaces target/gateway status as a result)
        # flows through unretried.
        res, exit_ip = _with_transport_retry(
            lambda: _fetch_via_api(creds, url, country, timeout)
        )
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
        # The real instant this capture was launched (see docstring), at full
        # precision so the batch dispatched_same_second verdict (max - min <= 1s)
        # is computed accurately. The batch reads these back off the records to
        # compute and stamp the canonical dispatch second.
        dispatched_at=_iso_instant(dispatched_at),
    )
    return record, fetched_at


def _iso_second(ts: datetime) -> str:
    """ISO-8601 ``...Z`` second-truncated stamp for a UTC instant."""
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_instant(ts: datetime) -> str:
    """ISO-8601 ``...Z`` MILLISECOND-precision stamp for a UTC instant.

    Used for ``dispatched_at`` so the batch dispatch spread (max - min) is
    computed accurately. The displayed dispatch FACT is second-truncated, but the
    stored value keeps sub-second precision so the <= 1s verdict is honest.
    """
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_iso_instant(value: str) -> datetime:
    """Parse a ``_iso_instant``/``_iso_second`` stamp back to an aware datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def dispatched_same_second(records: list[CaptureRecord]) -> bool:
    """The honest simultaneity verdict: were all captures DISPATCHED within 1s?

    Residential proxy fetches each take seconds, so a witnessed-same-second batch
    is physically impossible. The defensible claim is that the requests were
    LAUNCHED within the same second — which the concurrent dispatch achieves. This
    reads each record's full-precision ``dispatched_at`` and returns whether the
    spread (max - min) is <= 1s. Pure / deterministic given the records, so it is
    unit-tested with injected dispatch stamps (no live Bright Data required).

    Raises CaptureError if any record is missing a dispatch stamp (a record built
    outside the capture path) — never silently treats a missing stamp as true.
    """
    if not records:
        return True
    stamps: list[datetime] = []
    for rec in records:
        if not rec.dispatched_at:
            raise CaptureError(
                f"capture {rec.capture_id!r} has no dispatched_at; cannot compute "
                "dispatched_same_second honestly"
            )
        stamps.append(_parse_iso_instant(rec.dispatched_at))
    spread_seconds = (max(stamps) - min(stamps)).total_seconds()
    return spread_seconds <= 1.0


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


def same_second_batch_per_country_url(
    creds: BrightDataCredentials,
    country_urls: dict[str, str],
    sessions_per_country: int,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[CaptureRecord]:
    """Capture, per country, ITS OWN storefront URL x N sticky sessions, one batch.

    ``country_urls`` maps an ISO-2 country to the exact URL to fetch from THAT
    country's residential exits. This is the domain-per-country storefront case
    (the intra-EU norm: a German shopper sees ``mediamarkt.de``, a Belgian shopper
    sees ``mediamarkt.be`` — the same GTIN, two ccTLD storefronts). Each country's
    N distinct sticky sessions hit that country's URL from N distinct in-country
    residential exits (the within-country control). The geo claim is honest: the
    capture of the ``.de`` store is witnessed from a real German residential IP,
    the ``.be`` store from a real Belgian one.

    The geo-IP single-URL case (one URL whose CONTENT varies by visitor country)
    is :func:`same_second_batch`, which is this function with every country mapped
    to the same URL. Both share the identical same-second stamping discipline:
    each capture keeps its REAL fetch instant, and the actual batch spread decides
    the same-second verdict (<= 1s -> one canonical second; > 1s -> each record on
    its own real second, ``same_second_batch=false`` surfaced, never hidden).

    Raises CredentialsMissing if no creds; CaptureError on a real per-capture
    failure (the failing country + session are named).
    """
    if creds is None:
        raise CredentialsMissing("no Bright Data credentials available for capture")
    if not country_urls:
        raise CaptureError("same_second_batch_per_country_url: no country->URL mapping given")

    # Build the per-capture plan: distinct sticky session + capture_id per
    # (country, index). The (country, index) pair already makes every token in a
    # batch DISTINCT (=> a distinct residential exit, the within-country control);
    # a per-batch millisecond stamp makes a fresh RUN draw fresh sticky exits
    # rather than reusing the previous run's IPs.
    batch_stamp = int(time.time() * 1000)
    plan: list[_CapturePlan] = []
    for country, url in country_urls.items():
        for i in range(sessions_per_country):
            plan.append(
                _CapturePlan(
                    country=country,
                    url=url,
                    session=f"amber-{country.lower()}-{i + 1}-{batch_stamp}",
                    capture_id=f"{country.lower()}-{i + 1:02d}",
                )
            )

    if not plan:
        raise CaptureError(
            "same_second_batch_per_country_url: sessions_per_country must be >= 1 "
            f"(got {sessions_per_country})"
        )

    def _run(item: _CapturePlan) -> tuple[CaptureRecord, datetime]:
        try:
            return capture_one(
                creds, item.url, item.country, item.session, item.capture_id, timeout=timeout
            )
        except CaptureError as exc:
            # Name the failing country + session — never a silent drop.
            raise CaptureError(
                f"capture failed for {item.country} session {item.session} "
                f"({item.capture_id}): {exc}"
            ) from exc

    # Dispatch ALL captures CONCURRENTLY. Each capture_one is I/O-bound (proxy
    # discover + fetch), so threads launch the requests near-simultaneously: every
    # capture stamps its OWN dispatched_at at the instant its thread starts, and
    # those instants cluster within a second even though each fetch then takes
    # seconds. This is the honest "DISPATCHED same second" claim — distinct sticky
    # sessions are preserved (one per plan entry), so the within-country control is
    # intact. A failure in any worker propagates (first exception wins) — never a
    # fabricated or partial-but-silent batch.
    results: dict[str, tuple[CaptureRecord, datetime]] = {}
    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        futures = {pool.submit(_run, item): item for item in plan}
        for fut, item in futures.items():
            results[item.capture_id] = fut.result()

    # Re-assemble in deterministic capture_id order (independent of completion
    # order) so the batch output is stable run-to-run.
    ordered = [results[item.capture_id] for item in plan]
    records = [rec for rec, _ts in ordered]
    fetched_at = [ts for _rec, ts in ordered]

    stamp_batch_timestamps(records, fetched_at)
    return records


def same_second_batch(
    creds: BrightDataCredentials,
    url: str,
    countries: list[str],
    sessions_per_country: int,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[CaptureRecord]:
    """Capture ``url`` from every country x N sticky sessions in one batch.

    The geo-IP single-URL case: ONE URL whose served content varies by the
    visitor's country. Each capture is stamped with its REAL fetch wall-clock
    time. The actual batch spread (max - min of those real instants) decides the
    same-second claim: a spread <= 1s makes every record share one canonical
    second (the floor reports ``same_second_batch=true`` truthfully); a spread
    > 1s leaves each record on its own real second so the floor reports
    ``same_second_batch=false``. The wall-clock fetches are sequential —
    residential proxy fetches cannot be truly simultaneous from one process — and
    a batch that spans more than a second is reported honestly, never hidden.

    For the domain-per-country storefront case (a different URL per country, same
    GTIN) use :func:`same_second_batch_per_country_url`.

    Raises CredentialsMissing if no creds (the caller/harness reports the pending
    live step); raises CaptureError on a real per-capture failure after recording
    which session failed.
    """
    return same_second_batch_per_country_url(
        creds,
        {country: url for country in countries},
        sessions_per_country,
        timeout=timeout,
    )
