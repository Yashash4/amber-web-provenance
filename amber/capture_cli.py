"""Component-2 CLI: ``amber-capture`` — the live BD capture + measurement floor.

Subcommands:
  * ``capture``  — same-second DE/BE (+within-country-control) residential capture
                   of one URL -> floor -> seal -> verify_packet (GATE 2). Needs BD
                   creds; reports the pending live step if absent.
  * ``discover`` — run the floor across several candidate OWN-brand SKU URLs and
                   surface the strongest real finding (or an honest no-finding).
  * ``creds``    — print the SECRET-FREE credential state (which fields are set).

Nothing here fabricates data. With no Bright Data credentials present (env or the
gitignored code/.env), the live subcommands print a clear "pending creds" message
and exit non-zero so a script can tell the live step did not run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from amber.capture import credentials, discover, harness, vat

REPO = Path(__file__).resolve().parent.parent
DEFAULT_KEY_PATH = REPO / "amber" / "keys" / "demo-signer.key"


def _load_signing_key() -> str | None:
    """Load the sealing PRIVATE key (env AMBER_SIGNING_KEY or gitignored file)."""
    env = os.environ.get("AMBER_SIGNING_KEY", "").strip()
    if env:
        return env
    if DEFAULT_KEY_PATH.exists():
        return DEFAULT_KEY_PATH.read_text(encoding="ascii").strip()
    return None


def _trusted_pubkeys() -> set[str] | None:
    """Resolve trusted pubkeys for the verify step (env, else committed allowlist)."""
    env = os.environ.get("AMBER_TRUSTED_PUBKEY", "").strip()
    if env:
        return {tok.lower() for tok in env.replace(",", " ").split() if tok}
    return None  # harness/verify_packet falls back to the committed allowlist


def _cmd_creds(_args: argparse.Namespace) -> int:
    state = credentials.describe(credentials.load())
    sys.stdout.write(json.dumps(state, indent=2) + "\n")
    return 0 if state["present"] else 1


def _cmd_capture(args: argparse.Namespace) -> int:
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    key = _load_signing_key()
    result = harness.run(
        args.out,
        args.url,
        countries,
        args.sessions,
        key,
        category=args.category,
        sku_label=args.sku_label,
        trusted_pubkeys=_trusted_pubkeys(),
        timeout=args.timeout,
    )
    sys.stdout.write(json.dumps(result.as_report(), indent=2) + "\n")
    if not result.ran_live:
        sys.stdout.write("\n" + result.message + "\n")
        return 2  # pending creds (or no key) — live step did not run
    return 0 if result.verify_ok else 1


def _cmd_discover(args: argparse.Namespace) -> int:
    # candidate URLs: a JSON file of [["url","label"], ...] or [ "url", ... ].
    raw = json.loads(Path(args.candidates).read_bytes().decode("utf-8"))
    candidates: list[tuple[str, str | None]] = []
    for item in raw:
        if isinstance(item, str):
            candidates.append((item, None))
        else:
            candidates.append((item[0], item[1] if len(item) > 1 else None))
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    result = discover.discover(
        candidates, countries, args.sessions, category=args.category, timeout=args.timeout
    )
    sys.stdout.write(json.dumps(result.as_report(), indent=2) + "\n")
    if not result.ran_live:
        return 2
    return 0 if not result.no_finding else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amber-capture",
        description="Amber Component 2 — Bright Data residential capture + the "
        "deterministic measurement-validity floor.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_cap = sub.add_parser("capture", help="capture one URL across countries -> signed packet")
    p_cap.add_argument("url", help="the product URL to capture")
    p_cap.add_argument(
        "--out", default=str(REPO / "samples" / "live_packet"), help="packet out dir"
    )
    p_cap.add_argument("--countries", default="DE,BE", help="comma ISO-2 list (hero pair)")
    p_cap.add_argument(
        "--sessions", type=int, default=3, help="distinct residential exits per country (>=3)"
    )
    p_cap.add_argument("--category", default=vat.CATEGORY_STANDARD, help="VAT category")
    p_cap.add_argument("--sku-label", default=None, help="human label for the SKU")
    p_cap.add_argument("--timeout", type=int, default=45, help="per-fetch timeout seconds")
    p_cap.set_defaults(func=_cmd_capture)

    p_disc = sub.add_parser("discover", help="rank candidate SKUs for a real finding")
    p_disc.add_argument("candidates", help="JSON file of candidate URLs (or [url,label] pairs)")
    p_disc.add_argument("--countries", default="DE,BE", help="comma ISO-2 list")
    p_disc.add_argument("--sessions", type=int, default=3, help="exits per country")
    p_disc.add_argument("--category", default=vat.CATEGORY_STANDARD)
    p_disc.add_argument("--timeout", type=int, default=45)
    p_disc.set_defaults(func=_cmd_discover)

    p_creds = sub.add_parser("creds", help="print the secret-free credential state")
    p_creds.set_defaults(func=_cmd_creds)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
