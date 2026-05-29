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

# DECISIVE body markers: phrases that appear ONLY on an actual challenge /
# block INTERSTITIAL, never on a fully-served product page. Matched
# case-insensitively against the decoded body. Each of these is the page TELLING
# the visitor it is a challenge ("verifying you are human", "just a moment...",
# the explicit challenge form id ``cf-chl-``), so any one of them is a soft-block
# on its own.
#
# Root-cause note (why this list is short): a served page routinely *references*
# anti-bot tooling without BEING a challenge — Cloudflare injects its
# ``/cdn-cgi/challenge-platform`` Turnstile/JS-detections script into normal 200
# pages, the word "captcha" appears in privacy copy or a reCAPTCHA-enterprise
# script tag behind a contact form, and DataDome/Akamai/PerimeterX cookie/script
# tokens (``_abck``, ``_px``, ``datadome``) sit in the markup of fully-served
# pages. Treating those bare substrings as decisive flagged real 1.2 MB product
# pages (with a real schema.org price + GTIN) as "soft-blocked" — a false
# positive. They are demoted to WEAK markers below (corroborating only).
_BODY_MARKERS = (
    "cf-challenge",
    "cf-chl-",  # Cloudflare challenge form/script id (challenge page only)
    "just a moment",  # Cloudflare interstitial title
    "attention required",  # Cloudflare 1020/block title
    "g-recaptcha",  # an actually-rendered reCAPTCHA widget
    "h-captcha",
    "hcaptcha",
    "px-captcha",  # PerimeterX rendered challenge
    "are you a robot",
    "enable javascript and cookies",
    "verifying you are human",
    "checking your browser before",  # DDoS-Guard / CF interstitial line
    "unusual traffic",  # Google-style rate-limit interstitial
    "request blocked",
    "bot detection",
)

# WEAK body markers: anti-bot vendor SCRIPT/COOKIE tokens (and the generic word
# "captcha") that legitimately appear in the markup of FULLY-SERVED pages. These
# never decide a soft-block alone; they only corroborate one when paired with a
# block STATUS or a degenerate body. (Without that pairing, a real product page
# behind Cloudflare/DataDome/Akamai would be wrongly ruled INCONCLUSIVE.)
_WEAK_BODY_MARKERS = (
    "challenge-platform",  # CF Turnstile/JS-detections script on normal pages too
    "/cdn-cgi/challenge-platform",
    "captcha",  # bare word: privacy copy, reCAPTCHA-enterprise script refs, etc.
    "_px",  # PerimeterX cookie/script token
    "datadome",  # DataDome script/cookie present on served pages
    "imperva",
    "incapsula",
    "akamai",
    "_abck",  # Akamai Bot Manager cookie name in the markup
    "access denied",  # appears in copy; decisive only with a block status
)

# PRIMARY header markers: header substrings (lower-cased) that appear ONLY on a
# challenge / block response, not on a fully-served page. ``cf-mitigated`` is
# Cloudflare's challenge-response header; ``x-datadome``/``x-iinfo`` are the
# DataDome / Imperva block markers.
_HEADER_MARKERS = (
    "cf-mitigated",  # Cloudflare challenge response header
    "x-datadome",
    "x-iinfo",  # Imperva/Incapsula info header
)

# WEAK header markers: pure CDN-IDENTITY headers present on EVERY page that CDN
# serves (a 200-OK product page included). ``server: cloudflare`` and ``x-cdn``
# say "this site is behind a CDN", NOT "this response is a block" — so on their
# own they must not force INCONCLUSIVE (the false positive observed live: a real
# 200 MediaMarkt product page carries ``Server: cloudflare``). They corroborate
# only when a PRIMARY signal already fired.
_WEAK_HEADER_MARKERS = (
    "server: cloudflare",
    "x-cdn",
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

    Decision rule (root, not heuristic-soup) — PRIMARY signals decide a block;
    WEAK signals only corroborate one:
      - A soft-block STATUS (429/403/503) is a PRIMARY signal.
      - A Retry-After header is a PRIMARY signal (throttling).
      - A header vendor block-marker (e.g. ``cf-mitigated``) is a PRIMARY signal.
      - A DECISIVE body marker (an actual challenge title / rendered CAPTCHA
        widget / "verifying you are human") is a PRIMARY signal.
      - A WEAK body marker (an anti-bot vendor SCRIPT/COOKIE token, or the bare
        word "captcha") is CORROBORATING ONLY — it appears in the markup of
        fully-served pages, so it counts only when a PRIMARY signal also fired.
      - A degenerate (tiny) body is CORROBORATING ONLY (never decides alone).
    The capture is soft-blocked iff at least one PRIMARY signal fired. This keeps
    a real product page that merely embeds a Cloudflare/DataDome/Akamai script (a
    1.2 MB 200 OK with a genuine schema.org price + GTIN) from being mislabeled,
    while still catching real challenges, blocks, and throttles.
    """
    signals: list[str] = []
    headers_lc = {k.lower(): str(v).lower() for k, v in headers.items()}

    # --- PRIMARY signals (any one decides a soft-block) --------------------- #
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

    # 4. Decisive body markers (challenge-interstitial-only phrases).
    text = _decode_body(body)
    for marker in _BODY_MARKERS:
        if marker in text:
            signals.append(f"body-marker:{marker}")

    has_primary = len(signals) > 0

    # --- CORROBORATING signals (recorded only when a PRIMARY signal fired) -- #
    # Weak vendor script/cookie tokens + CDN-identity headers: present on served
    # pages too, so they are logged for the audit trail but only when a real block
    # is already indicated.
    if has_primary:
        weak_header_hits = [m for m in _WEAK_HEADER_MARKERS if m in header_blob]
        signals.extend(f"weak-header-marker:{m}" for m in weak_header_hits)
        weak_body_hits = [m for m in _WEAK_BODY_MARKERS if m in text]
        signals.extend(f"weak-body-marker:{m}" for m in weak_body_hits)

    # Degenerate body — corroborating only.
    if len(body) < _DEGENERATE_BODY_BYTES and has_primary:
        signals.append(f"degenerate-body:{len(body)}B")

    return SoftBlockResult(is_soft_blocked=has_primary, signals=signals)


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
