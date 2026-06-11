"""Pure classified-retry + jittered-backoff policy for the BD capture transport.

This is the Python port of the resilience policy Amber contributed upstream to
Bright Data's MCP (PR #155): the ``classify_response`` / ``compute_backoff`` /
``should_retry`` taxonomy that lets a multi-geo same-second capture batch survive
a transient gateway hiccup (a 502/504 from the super-proxy, a connection reset, a
timeout) instead of failing the whole batch on the first blip.

Everything here is PURE: no network, no sleeping, no clock except an INJECTED
``now_ms``/``rng``, so the policy is table-testable in isolation exactly like the
JS original (and like the rest of this package, which unit-tests with injected
clocks and rngs). The :mod:`amber.capture.brightdata` transport consumes these
helpers; the actual fetch, sleep, and CaptureError live there.

★ THE FORENSIC GUARD (why a returned status is treated differently here than in
the JS port): in Amber, ``_fetch_via_proxy`` NEVER raises on a target HTTP status
(a 403/451/503 from the target site is a real, capturable result that the floor
classifies). Retry in Amber therefore applies ONLY to THROWN transport failures
(the connection never produced a capturable response): a ``requests`` /
``urllib`` transport exception, a reset, a timeout, a transient TLS/proxy-auth
blip. A returned target status is a RESULT, never a retry trigger. The status
classifier below (``classify_status``) is kept complete and faithful to #155 so
the policy is a true port and is reusable, but the brightdata integration only
ever feeds it the GATEWAY signal carried on a thrown error, never a captured
target status. This keeps the instrument honest: a retry re-attempts a real
fetch on the SAME sticky session (same residential exit) and never fabricates a
body, status, IP, or country.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

# --------------------------------------------------------------------------- #
# Outcome taxonomy (mirrors PR #155's OUTCOME). Each value tells the caller what
# to do next, independent of any particular transport library.
# --------------------------------------------------------------------------- #
OUTCOME_SUCCESS = "success"  # 2xx: use the body.
OUTCOME_REDIRECT = "redirect"  # 3xx: follow the Location (not an error).
OUTCOME_RETRYABLE = "retryable"  # transient: safe to retry after a backoff.
OUTCOME_RATE_LIMITED = "rate_limited"  # 429: retry, honoring Retry-After if given.
OUTCOME_BLOCKED = "blocked"  # target actively blocked us (403/451): terminal.
OUTCOME_CLIENT_ERROR = "client_error"  # 4xx caller mistake: terminal.
OUTCOME_FATAL = "fatal"  # unexpected / unclassifiable: terminal.

# Gateway/transport statuses that are safe to retry. 502/504 are the exact
# symptoms reported in issue #104; 408/425 are slow/early-data conditions and
# 500/503 are transient server states.
RETRYABLE_STATUS: frozenset[int] = frozenset({408, 425, 500, 502, 503, 504})

# Statuses that mean "the target refused us"; retrying the same request will not
# help, so we surface them as a first-class BLOCKED outcome rather than burning
# retries or discarding the signal.
BLOCKED_STATUS: frozenset[int] = frozenset({403, 451})

# Transient socket/OS error number symbols (errno names) with no HTTP status
# attached. These are connectivity failures and are safe to retry on the same
# session. The Python analogue of #155's RETRYABLE_NETWORK_CODES (Node errno
# strings); we match on the OSError ``errno`` name so it is platform-stable.
RETRYABLE_ERRNO_NAMES: frozenset[str] = frozenset(
    {
        "ECONNRESET",
        "ECONNREFUSED",
        "ECONNABORTED",
        "ETIMEDOUT",
        "EPIPE",
        "ENETUNREACH",
        "ENETRESET",
        "EHOSTUNREACH",
        "WSAECONNRESET",  # the Windows winsock spellings of the same conditions
        "WSAECONNREFUSED",
        "WSAECONNABORTED",
        "WSAETIMEDOUT",
        "WSAENETUNREACH",
        "WSAENETRESET",
        "WSAEHOSTUNREACH",
    }
)

# An HTTP-date per RFC 9110 begins with a recognizable day-name prefix. We
# require it so a bare number-like string ('1.5', '-3') is NEVER fed to a
# permissive date parser (which could read it as a past date and clamp to an
# immediate retry). Mirrors #155's HTTP_DATE_RE strictness.
_HTTP_DATE_RE = re.compile(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*[,\s]", re.IGNORECASE)
_INTEGER_RE = re.compile(r"^\d+$")


@dataclass(frozen=True)
class Classification:
    """The result of classifying a response/error: outcome + retry metadata.

    ``retryable`` is the single boolean a retry loop checks; ``retry_after_ms``
    (when present) is a server-supplied wait that overrides the computed backoff.
    ``reason`` is a short human string for logging (never a secret).
    """

    outcome: str
    status: int | None
    retry_after_ms: int | None
    retryable: bool
    reason: str


@dataclass(frozen=True)
class BackoffOpts:
    """Exponential-backoff knobs. ``base_ms`` doubles by ``factor`` each attempt
    up to ``max_ms``, then ``jitter`` is applied so concurrent captures (the
    same-second batch) do not retry in lockstep and re-overload the gateway.

    ``jitter`` is one of ``"full"`` (default: uniform in [0, capped]), ``"equal"``
    (AWS equal jitter: half fixed, half random), or ``"none"`` (deterministic).
    """

    base_ms: float = 500.0
    max_ms: float = 30000.0
    factor: float = 2.0
    jitter: str = "full"


# Default policy: mirrors #155's DEFAULT_BACKOFF.
DEFAULT_BACKOFF = BackoffOpts()


@dataclass(frozen=True)
class RetryDecision:
    """Whether to retry, and the delay (ms) to wait first. ``classification`` is
    carried through so a loop has everything it needs in one object."""

    retry: bool
    delay_ms: float
    classification: Classification | None


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_retry_after(value: object, now_ms: float) -> int | None:
    """Parse a ``Retry-After`` header (RFC 9110) into milliseconds.

    The value is either a non-negative integer number of seconds or an HTTP-date.
    Returns milliseconds, or ``None`` if absent/malformed (so the caller falls
    back to its computed backoff rather than retrying immediately). A malformed
    value (fractional ``'1.5'``, negative ``'-3'``, junk) returns ``None``, NOT
    ``0``: this is the exact strictness #155 added so permissive date parsing
    never turns numeric junk into an immediate retry. ``now_ms`` is injected so
    HTTP-date cases are deterministic under test.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    # (a) a non-negative integer number of seconds.
    if _INTEGER_RE.match(raw):
        return int(raw) * 1000
    # (b) a valid HTTP-date. Reject anything not date-shaped up front so a
    # permissive parser never silently accepts numeric junk as a past date.
    if not _HTTP_DATE_RE.match(raw):
        return None
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    when_ms = when.timestamp() * 1000.0
    delta = when_ms - now_ms
    return int(delta) if delta > 0 else 0


def classify_status(
    status: int | None, headers: dict[str, str] | None, now_ms: float
) -> Classification:
    """Classify a completed-HTTP status into a stable :class:`Classification`.

    ``headers`` may be ``None`` (only a status known). ``retry-after`` is read
    case-insensitively. This is the faithful port of #155's status branch; in
    Amber it is fed the GATEWAY status carried on a thrown transport error, never
    a captured target status (see the module docstring's forensic guard).
    """
    retry_after_ms = parse_retry_after(_get_header(headers, "retry-after"), now_ms)

    if status is None:
        return Classification(
            outcome=OUTCOME_FATAL,
            status=None,
            retry_after_ms=None,
            retryable=False,
            reason="no status",
        )

    if 200 <= status < 300:
        return Classification(OUTCOME_SUCCESS, status, None, False, f"http {status}")

    # 3xx is a redirect, not an error: a terminal-for-this-call signal to
    # follow/report, neither retryable nor fatal (its own outcome).
    if 300 <= status < 400:
        return Classification(OUTCOME_REDIRECT, status, None, False, f"http {status} redirect")

    if status == 429:
        return Classification(
            OUTCOME_RATE_LIMITED, status, retry_after_ms, True, "http 429 rate limited"
        )

    if status in BLOCKED_STATUS:
        return Classification(
            OUTCOME_BLOCKED, status, None, False, f"http {status} target blocked request"
        )

    if status in RETRYABLE_STATUS:
        return Classification(
            OUTCOME_RETRYABLE,
            status,
            retry_after_ms,
            True,
            f"http {status} transient gateway error",
        )

    if 400 <= status < 500:
        return Classification(
            OUTCOME_CLIENT_ERROR, status, None, False, f"http {status} client error"
        )

    # Any other 5xx we did not enumerate: transient by nature, retryable, but
    # capped by the caller's max_retries.
    if status >= 500:
        return Classification(
            OUTCOME_RETRYABLE, status, retry_after_ms, True, f"http {status} server error"
        )

    return Classification(OUTCOME_FATAL, status, None, False, f"http {status} unclassified")


def classify_transport_error(exc: BaseException) -> Classification:
    """Classify a THROWN transport exception (no capturable response produced).

    This is the path Amber's retry actually uses: ``_fetch_via_proxy`` raises on
    a ``requests`` transport failure, ``_fetch_via_api`` raises on a ``urllib`` /
    socket failure. We inspect the exception tree for the transient signatures
    that #155's RETRYABLE_NETWORK_CODES captured (connection reset, refused,
    timeout, broken pipe, unreachable network/host) plus the ``requests`` /
    ``urllib`` transient exception TYPES, and return RETRYABLE for those. A
    proxy-auth ``407`` carried as a transient ProxyError is retryable on the same
    session (a transient gateway auth blip), but a definitively terminal failure
    is FATAL so the budget is never burned on a hopeless retry.

    Pure: it only reads the exception object, never touches the network.
    """
    # An OSError (which ECONNRESET/ETIMEDOUT/etc. ultimately are) carries an
    # errno; match its symbolic name so the decision is platform-stable.
    errno_name = _errno_name_of(exc)
    if errno_name and errno_name in RETRYABLE_ERRNO_NAMES:
        return Classification(
            OUTCOME_RETRYABLE, None, None, True, f"transport error {errno_name}"
        )

    # Transient transport exception TYPES, matched by class NAME so this module
    # imports no transport library (stays dependency-free + import-light). These
    # are the same conditions #155 retried: connection errors, timeouts, chunked
    # encoding / protocol resets mid-stream, and a transient proxy tunnel blip.
    transient_type_names = {
        "ConnectionError",  # requests.exceptions.ConnectionError + builtins
        "ConnectTimeout",
        "ReadTimeout",
        "Timeout",
        "TimeoutError",
        "ChunkedEncodingError",
        "ProtocolError",
        "ProxyError",
        "ConnectionResetError",
        "ConnectionAbortedError",
        "ConnectionRefusedError",
        "BrokenPipeError",
        "IncompleteRead",
        "RemoteDisconnected",
    }
    for klass in type(exc).__mro__:
        if klass.__name__ in transient_type_names:
            return Classification(
                OUTCOME_RETRYABLE, None, None, True, f"transport error {type(exc).__name__}"
            )

    # An unrecognized transport failure is FATAL: surfaced, never silently
    # retried (a hopeless retry would just delay the honest failure).
    return Classification(
        OUTCOME_FATAL, None, None, False, f"unhandled transport error {type(exc).__name__}"
    )


def compute_backoff(
    attempt: int,
    opts: BackoffOpts = DEFAULT_BACKOFF,
    rng: Callable[[], float] = None,  # type: ignore[assignment]
    *,
    retry_after_ms: int | None = None,
) -> float:
    """Compute the delay (ms) before retry ``attempt`` (0-indexed: attempt 0 is
    the wait before the 2nd try).

    A server-supplied ``retry_after_ms`` always wins and is clamped to
    ``opts.max_ms``. Otherwise: exponential ``base_ms * factor**attempt`` capped
    at ``max_ms``, then jitter. ``rng`` is injected (defaults to a real PRNG only
    when called without one) so jittered delays are deterministic under test.
    Mirrors #155's compute_backoff exactly, including the full-jitter default.
    """
    if rng is None:  # pragma: no cover - the transport always injects a real rng
        import random

        rng = random.random

    base_ms = (
        opts.base_ms
        if _is_finite_number(opts.base_ms) and opts.base_ms >= 0
        else DEFAULT_BACKOFF.base_ms
    )
    max_ms = (
        opts.max_ms
        if _is_finite_number(opts.max_ms) and opts.max_ms >= 0
        else DEFAULT_BACKOFF.max_ms
    )
    factor = (
        opts.factor
        if _is_finite_number(opts.factor) and opts.factor >= 1
        else DEFAULT_BACKOFF.factor
    )
    jitter = opts.jitter

    # A server Retry-After wins, clamped to the max.
    if retry_after_ms is not None and _is_finite_number(retry_after_ms) and retry_after_ms >= 0:
        return min(float(retry_after_ms), max_ms)

    safe_attempt = int(math.floor(attempt)) if _is_finite_number(attempt) and attempt > 0 else 0
    exponential = base_ms * (factor**safe_attempt)
    capped = min(exponential, max_ms)

    if jitter == "none":
        return capped
    if jitter == "equal":
        # AWS "equal jitter": half fixed, half random.
        half = capped / 2.0
        return round(half + rng() * half)
    # "full jitter" (default): uniform random in [0, capped].
    return round(rng() * capped)


def should_retry(
    classification: Classification | None,
    attempt: int,
    max_retries: int,
    opts: BackoffOpts = DEFAULT_BACKOFF,
    rng: Callable[[], float] = None,  # type: ignore[assignment]
) -> RetryDecision:
    """Decide whether to retry given a classification and the remaining budget.

    ``attempt`` is 0-indexed (0 = the first try just failed). Returns a
    :class:`RetryDecision` with ``retry`` + the ``delay_ms`` to wait first
    (honoring a server ``retry_after_ms`` when the classification carries one).
    Mirrors #155's should_retry budget logic exactly.
    """
    safe_max = (
        int(math.floor(max_retries))
        if _is_finite_number(max_retries) and max_retries >= 0
        else 0
    )
    if classification is None or not classification.retryable:
        return RetryDecision(False, 0.0, classification)
    if attempt >= safe_max:
        return RetryDecision(False, 0.0, classification)
    delay_ms = compute_backoff(
        attempt, opts, rng, retry_after_ms=classification.retry_after_ms
    )
    return RetryDecision(True, delay_ms, classification)


def _get_header(headers: dict[str, str] | None, name: str) -> str | None:
    """Read a header case-insensitively from a plain dict (any casing)."""
    if not headers or not isinstance(headers, dict):
        return None
    target = name.lower()
    for key, val in headers.items():
        if isinstance(key, str) and key.lower() == target:
            return val
    return None


def _errno_name_of(exc: BaseException) -> str | None:
    """The symbolic errno name (e.g. ``"ECONNRESET"``) of an exception, walking
    its ``__cause__``/``__context__`` chain to find the underlying ``OSError``.

    ``requests`` wraps the socket error several layers deep, so the transient
    errno lives on a chained cause, not the top exception. We walk the chain so a
    wrapped reset/timeout is still recognized as retryable.
    """
    import errno as _errno

    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        err = getattr(cur, "errno", None)
        if isinstance(err, int):
            name = _errno.errorcode.get(err)
            if name:
                return name
        cur = cur.__cause__ or cur.__context__
    return None
