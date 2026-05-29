"""Live-capture harness: capture -> floor -> seal_packet -> verify_packet.

This is the end-to-end GATE-2 runner. The MOMENT Bright Data credentials are
present (env or the gitignored ``code/.env``) it performs a real same-second,
multi-country, multi-session residential capture of a product URL, computes the
deterministic Layer-1 facts, seals a signed Amber packet (Component 1), and
verifies it GREEN against the pinned signer key.

When credentials are ABSENT it does NOT run a live capture and does NOT fabricate
anything — it returns a clear "pending: BD credentials" result. The full
deterministic floor is still exercisable offline via :func:`seal_from_records`
against constructed records (used by the unit tests), so everything except the
real network step is verified without creds.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from amber.capture import brightdata, credentials, floor, vat
from amber.capture.record import CaptureRecord
from amber.packet import seal_packet, verify_packet


@dataclass
class HarnessResult:
    """Outcome of a harness run."""

    ran_live: bool
    packet_dir: Path | None
    facts: dict | None
    verify_ok: bool | None
    cred_state: dict = field(default_factory=dict)
    message: str = ""

    def as_report(self) -> dict:
        return {
            "ran_live": self.ran_live,
            "packet_dir": str(self.packet_dir) if self.packet_dir else None,
            "verify_ok": self.verify_ok,
            "cred_state": self.cred_state,
            "message": self.message,
            "primary_finding": (
                self.facts["cross_country_comparison"]["primary_finding"]
                if self.facts
                else None
            ),
        }


def seal_from_records(
    out_dir: str | Path,
    url: str | dict[str, str],
    records: list[CaptureRecord],
    private_key_hex: str,
    *,
    category: str = vat.CATEGORY_STANDARD,
    sku_label: str | None = None,
    trusted_pubkeys: set[str] | None = None,
) -> HarnessResult:
    """Floor -> seal -> verify, given already-captured records.

    Shared by the live path and the offline unit tests. Builds ``facts.json`` via
    the deterministic floor, seals the packet from the records' real bodies, and
    re-verifies it. ``trusted_pubkeys`` pins the verify step (the unit tests pass
    the ephemeral test key; the demo defaults to the committed allowlist).
    """
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)

    facts = floor.build_facts(url, records, category=category, sku_label=sku_label)
    pairs = [(r.to_capture_input(), r.body) for r in records]
    seal_packet(out, pairs, facts, private_key_hex)

    result = verify_packet(out, expected_pubkeys=trusted_pubkeys)
    return HarnessResult(
        ran_live=False,
        packet_dir=out,
        facts=facts,
        verify_ok=result.ok,
        message=(
            f"sealed {len(records)} captures; verify_packet="
            f"{'GREEN' if result.ok else 'RED (' + str(result.broken_node) + ')'}"
        ),
    )


def run(
    out_dir: str | Path,
    url: str,
    countries: list[str],
    sessions_per_country: int,
    private_key_hex: str | None,
    *,
    country_urls: dict[str, str] | None = None,
    category: str = vat.CATEGORY_STANDARD,
    sku_label: str | None = None,
    trusted_pubkeys: set[str] | None = None,
    timeout: int = brightdata.DEFAULT_TIMEOUT,
) -> HarnessResult:
    """Run the full live pipeline if creds are present; else report pending.

    Two capture shapes:
      * geo-IP single-URL (default): fetch ``url`` from every country in
        ``countries`` (one URL, content varies by visitor country).
      * domain-per-country storefronts: pass ``country_urls`` ({country: url}) to
        fetch each country's OWN storefront URL from that country's residential
        exits (same GTIN, two ccTLD stores — the intra-EU norm). When given,
        ``country_urls`` takes precedence and ``url``/``countries`` are ignored.

    Returns a :class:`HarnessResult`. ``ran_live`` is False with a clear message
    when BD credentials are absent (the one pending step) — never a fabricated
    packet.
    """
    creds = credentials.load()
    cred_state = credentials.describe(creds)

    if creds is None:
        return HarnessResult(
            ran_live=False,
            packet_dir=None,
            facts=None,
            verify_ok=None,
            cred_state=cred_state,
            message=(
                "Bright Data credentials ABSENT (checked env + code/.env). Live "
                "capture is the one pending step. The deterministic floor + "
                "seal/verify pipeline are fully built and unit-tested offline; "
                "set BRIGHTDATA_CUSTOMER_ID/ZONE/ZONE_PASSWORD (or "
                "BRIGHTDATA_API_TOKEN) and re-run to perform the real capture and "
                "hit GATE 2 for real."
            ),
        )

    if not private_key_hex:
        raise ValueError(
            "run(): a signing private key is required for the live seal step "
            "(creds are present). Pass private_key_hex (env AMBER_SIGNING_KEY)."
        )

    if country_urls:
        records = brightdata.same_second_batch_per_country_url(
            creds, country_urls, sessions_per_country, timeout=timeout
        )
        facts_url: str | dict[str, str] = dict(country_urls)
    else:
        records = brightdata.same_second_batch(
            creds, url, countries, sessions_per_country, timeout=timeout
        )
        facts_url = url
    sealed = seal_from_records(
        out_dir,
        facts_url,
        records,
        private_key_hex,
        category=category,
        sku_label=sku_label,
        trusted_pubkeys=trusted_pubkeys,
    )
    sealed.ran_live = True
    sealed.cred_state = cred_state
    sealed.message = "LIVE: " + sealed.message
    return sealed
