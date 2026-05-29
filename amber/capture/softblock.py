"""Anti-bot / soft-block detection — the credibility gate.

A "soft block" is when the site did NOT serve the real product page but instead
a CAPTCHA, a JS interstitial, a rate-limit page, or a degraded/empty response.
Its danger is subtle: an anti-bot page often *contains geo-reason text* ("not
available in your region") that LOOKS like a genuine geo-block. If Amber trusted
that text it would declare a fake GEO_BLOCKED — a false positive that a judge
would kill on the first question.

So the rule (LOCK / honesty rule #8): **a detected soft-block forces the state to
INCONCLUSIVE regardless of any geo-reason text**, and the suspected block must be
re-tested from a clean in-country IP before it can ever become GEO_BLOCKED. This
module is the deterministic detector; the floor enforces the consequence.

Detection is signal-based, not vibe-based: each detected signal is recorded by
name so the fact says *why* it was ruled inconclusive (a Daubert "characterized
error mode"). We look at the HTTP status, well-known anti-bot vendor markers,
challenge-script fingerprints, and degenerate-body heuristics — all computed from
the captured bytes + headers, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# HTTP statuses that, on their own, indicate a throttle/forbidden anti-bot
# response rather than a genuine product-availability answer.
_SOFT_BLOCK_STATUSES = {429, 403, 503}

# Vendor / challenge markers commonly present in anti-bot interstitials. Matched
# case-insensitively against the decoded body and against header values. These
# are deliberately specific strings, not generic words, to keep false positives
# low.
_BODY_MARKERS = (
    "cf-challenge",
    "cf-chl-",
    "challenge-platform",  # Cloudflare challenge bundle path
    "/cdn-cgi/challenge-platform",
    "just a moment",  # Cloudflare interstitial title
    "attention required",  # Cloudflare 1020/block title
    "captcha",
    "g-recaptcha",
    "h-captcha",
    "hcaptcha",
    "px-captcha",  # PerimeterX
    "_px",  # PerimeterX cookie/script token
    "datadome",  # DataDome
    "imperva",
    "incapsula",  # Imperva/Incapsula
    "akamai",  # Akamai Bot Manager (with the script marker below)
    "_abck",  # Akamai Bot Manager cookie name appearing in body
    "are you a robot",
    "enable javascript and cookies",
    "verifying you are human",
    "unusual traffic",  # Google-style rate-limit interstitial
    "access denied",
    "request blocked",
    "bot detection",
)

# Header markers (header-name or header-value substrings, lower-cased).
_HEADER_MARKERS = (
    "cf-mitigated",  # Cloudflare challenge response header
    "x-datadome",
    "x-iinfo",  # Imperva/Incapsula info header
    "x-cdn",
    "server: cloudflare",  # combined with a block status, corroborates
)

# A retry-after header strongly implies throttling.
_RETRY_AFTER = "retry-after"

# Bodies smaller than this (bytes) for a product page are suspiciously degenerate
# (an interstitial or an empty/stub response), corroborating a soft-block when
# paired with another signal. NOT a sole trigger — a legitimately tiny JSON API
# response exists — so it only contributes, never decides alone.
_DEGENERATE_BODY_BYTES = 512


@dataclass
class SoftBlockResult:
    """The soft-block verdict for one capture.

    ``is_soft_blocked`` True means the capture must be treated as INCONCLUSIVE.
    ``signals`` names every contributing marker so the fact is auditable.
    """

    is_soft_blocked: bool
    signals: list[str] = field(default_factory=list)

    def as_fact(self) -> dict:
        return {"is_soft_blocked": self.is_soft_blocked, "signals": list(self.signals)}


def _decode_body(body: bytes) -> str:
    """Best-effort lower-cased text view of the body for marker scanning.

    Anti-bot pages are HTML/text; binary product images aren't product pages.
    Decoding errors are replaced (never raised) — a body we can't decode simply
    yields fewer text markers, which is safe (it can't manufacture a false block).
    """
    return body.decode("utf-8", errors="replace").lower()


def detect(
    http_status: int,
    headers: dict[str, str],
    body: bytes,
) -> SoftBlockResult:
    """Deterministically detect an anti-bot / soft-block response.

    Decision rule (root, not heuristic-soup):
      - A soft-block STATUS (429/403/503) is itself a soft-block signal.
      - A Retry-After header is a soft-block signal.
      - Any known vendor/challenge marker in the body or headers is a signal.
      - A degenerate (tiny) body is a *corroborating* signal that only counts
        when at least one other signal is present (never decides alone).
    The capture is soft-blocked iff at least one non-corroborating signal fired
    (or a corroborating signal is backed by another). This keeps a legitimately
    small 200 OK API body from being mislabeled, while catching real challenges.
    """
    signals: list[str] = []
    headers_lc = {k.lower(): str(v).lower() for k, v in headers.items()}

    # 1. Status-based.
    if http_status in _SOFT_BLOCK_STATUSES:
        signals.append(f"http_status={http_status}")

    # 2. Retry-After header (throttling).
    if _RETRY_AFTER in headers_lc:
        signals.append("retry-after-header")

    # 3. Header vendor markers.
    header_blob = " ".join(f"{k}: {v}" for k, v in headers_lc.items())
    for marker in _HEADER_MARKERS:
        if marker in header_blob:
            signals.append(f"header-marker:{marker}")

    # 4. Body vendor/challenge markers.
    text = _decode_body(body)
    for marker in _BODY_MARKERS:
        if marker in text:
            signals.append(f"body-marker:{marker}")

    # 5. Degenerate body — corroborating only.
    degenerate = len(body) < _DEGENERATE_BODY_BYTES
    has_primary = len(signals) > 0
    if degenerate and has_primary:
        signals.append(f"degenerate-body:{len(body)}B")

    is_blocked = has_primary
    return SoftBlockResult(is_soft_blocked=is_blocked, signals=signals)


# A small set of regexes that detect explicit *geo-reason* language. The floor
# uses this ONLY as one candidate GEO_BLOCKED signal; per the honesty rule it is
# disregarded entirely whenever a soft-block is detected, so geo-reason text on a
# CAPTCHA page never produces a false GEO_BLOCKED.
_GEO_REASON_PATTERNS = (
    re.compile(r"not available in your (country|region|location)", re.I),
    re.compile(r"cannot ship to your (country|region|location)", re.I),
    re.compile(r"not sold in your (country|region)", re.I),
    re.compile(r"this (item|product) is not available in", re.I),
    re.compile(r"we do not (ship|deliver) to", re.I),
    re.compile(r"(unavailable|restricted) in your (country|region)", re.I),
)


def detect_geo_reason_text(body: bytes) -> str | None:
    """Return the matched geo-reason phrase if the body contains one, else None.

    Deterministic regex scan. NOTE: a positive here is only a *candidate* signal
    for GEO_BLOCKED; :mod:`amber.capture.state` discards it when a soft-block is
    present and requires a SECOND causally-independent signal regardless.
    """
    text = body.decode("utf-8", errors="replace")
    for pat in _GEO_REASON_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None
