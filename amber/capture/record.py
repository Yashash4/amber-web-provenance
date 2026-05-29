"""The CaptureRecord — the bridge between the BD client and the floor.

A :class:`CaptureRecord` is one residential fetch: the raw response body plus the
deterministic metadata observed about that fetch (exit IP, country, timestamp,
status, selected geo-signal headers). It carries everything the floor needs to
compute Layer-1 facts and everything Component 1 needs to seal the bytes.

This is a pure data object — no network, no parsing logic — so the floor can be
unit-tested against constructed records without Bright Data, and the same record
shape comes back from a real BD capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from amber.packet import CaptureInput

# Header names we always retain as Layer-1 geo/identity signals (lower-cased).
SELECTED_HEADERS = (
    "content-type",
    "content-language",
    "content-currency",
    "x-currency",
    "accept-language",  # echoed by some servers
    "location",
    "set-cookie",
    "vary",
    "retry-after",
    "cf-mitigated",
    "server",
    "date",
    "content-length",
)


def select_headers(headers: dict[str, str]) -> dict[str, str]:
    """Retain only the selected geo/identity-signal headers (lower-cased keys)."""
    lower = {k.lower(): v for k, v in headers.items()}
    return {h: lower[h] for h in SELECTED_HEADERS if h in lower}


@dataclass
class CaptureRecord:
    """One residential capture of a product URL.

    ``body`` is the exact bytes returned. ``proxy_reported_country`` is the
    country Bright Data says the exit was in (a Source-1 input for attribution);
    ``requested_country`` is what we asked for. ``session_id`` distinguishes the
    distinct residential IPs within a country (the within-country control).
    """

    capture_id: str
    url: str
    requested_country: str
    session_id: str
    exit_ip: str
    requested_at: str  # ISO-8601, same-second across a batch
    http_status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    proxy_reported_country: str | None = None

    def selected_headers(self) -> dict[str, str]:
        return select_headers(self.headers)

    def to_capture_input(self) -> CaptureInput:
        """Convert to Component 1's :class:`~amber.packet.CaptureInput`.

        Only the SELECTED geo-signal headers are sealed (the full header set is
        not — sealing every header would bloat the packet and leak proxy
        internals). The country recorded is the REQUESTED country; the
        attribution fact (in facts.json) carries the verified country evidence.
        """
        return CaptureInput(
            capture_id=self.capture_id,
            url=self.url,
            country=self.requested_country,
            exit_ip=self.exit_ip,
            requested_at=self.requested_at,
            http_status=self.http_status,
            headers=self.selected_headers(),
        )
