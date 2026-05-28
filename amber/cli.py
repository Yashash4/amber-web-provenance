"""Command-line entry points: ``verify_packet`` and ``seal_packet``.

``verify_packet`` is the demo instrument — it re-verifies a sealed packet fully
offline and prints a GREEN "VERIFIED" / RED "CHAIN OF CUSTODY BROKEN" verdict,
exiting 0 / non-zero respectively. THE TAMPER PROOF runs this live: edit the
exported packet → RED → revert → GREEN.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from amber.packet import VerifyResult, load_trusted_signers, verify_packet

# ANSI colours, auto-disabled when stdout is not a TTY or NO_COLOR is set.
_RESET = "\033[0m"
_GREEN = "\033[1;32m"
_RED = "\033[1;31m"
_DIM = "\033[2m"


def _supports_color(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("AMBER_FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


def _c(text: str, color: str, stream) -> str:
    return f"{color}{text}{_RESET}" if _supports_color(stream) else text


def _print_report(result: VerifyResult, packet_dir: Path, stream) -> None:
    stream.write(f"verify_packet: {packet_dir}\n")
    for node, ok, detail in result.checks:
        mark = _c("OK  ", _GREEN, stream) if ok else _c("FAIL", _RED, stream)
        stream.write(f"  [{mark}] {node}: {detail}\n")
    stream.write("\n")
    if result.ok:
        stream.write(_c("  [OK] VERIFIED -- chain of custody intact\n", _GREEN, stream))
    else:
        stream.write(_c("  [X] CHAIN OF CUSTODY BROKEN\n", _RED, stream))
        broken = result.broken_node or "(unknown)"
        stream.write(
            _c(f"  broken at: {broken}\n", _RED, stream)
            + _c(f"  {result.detail}\n", _DIM, stream)
        )


def _hex_pubkey(value: str) -> str:
    """argparse type: validate a 64-char (32-byte) hex ed25519 public key."""
    v = value.strip().lower()
    try:
        raw = bytes.fromhex(v)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not valid hex: {value!r}") from exc
    if len(raw) != 32:
        raise argparse.ArgumentTypeError(
            f"ed25519 public key must be 32 bytes (64 hex chars), got {len(raw)}"
        )
    return v


def _resolve_trusted(cli_pubkeys: list[str] | None) -> tuple[set[str], str]:
    """Resolve the trusted signer set + a human label of where it came from.

    Precedence: explicit ``--pubkey`` (repeatable) > ``AMBER_TRUSTED_PUBKEY``
    (comma/space separated) > the committed ``amber/keys/trusted_signers.txt``
    allowlist. The committed allowlist is the default so a fresh clone verifies
    the golden packet GREEN against the pinned demo key with no extra flags.
    """
    if cli_pubkeys:
        return {k.lower() for k in cli_pubkeys}, "--pubkey (CLI)"
    env = os.environ.get("AMBER_TRUSTED_PUBKEY", "").strip()
    if env:
        keys = {tok.lower() for tok in env.replace(",", " ").split() if tok}
        return keys, "AMBER_TRUSTED_PUBKEY env"
    return load_trusted_signers(), "committed allowlist (amber/keys/trusted_signers.txt)"


def main(argv: list[str] | None = None) -> int:
    """``verify_packet <packet_dir>`` — offline re-verification. Exit 0=GREEN.

    The signature is pinned to a trusted signer public key supplied out-of-band
    (``--pubkey`` / ``AMBER_TRUSTED_PUBKEY`` / the committed allowlist), never
    solely the key inside the packet — this is what makes the tamper-proof real.
    """
    parser = argparse.ArgumentParser(
        prog="verify_packet",
        description="Offline re-verify an Amber evidence packet "
        "(recompute every hash + Merkle root + verify the ed25519 signature "
        "against a PINNED trusted signer key).",
    )
    parser.add_argument("packet_dir", help="path to the sealed amber_packet/ directory")
    parser.add_argument(
        "--pubkey",
        type=_hex_pubkey,
        action="append",
        metavar="HEX",
        help="trusted signer ed25519 public key (64 hex chars); repeatable. "
        "Overrides AMBER_TRUSTED_PUBKEY and the committed allowlist.",
    )
    args = parser.parse_args(argv)

    packet_dir = Path(args.packet_dir)
    if not packet_dir.is_dir():
        sys.stderr.write(
            _c(
                f"verify_packet: not a directory: {packet_dir}\n",
                _RED,
                sys.stderr,
            )
        )
        return 2

    trusted, source = _resolve_trusted(args.pubkey)
    sys.stdout.write(
        f"trusted signer source: {source} "
        f"({len(trusted)} key{'s' if len(trusted) != 1 else ''})\n"
    )
    result = verify_packet(packet_dir, expected_pubkeys=trusted)
    _print_report(result, packet_dir, sys.stdout)
    return 0 if result.ok else 1


def seal_main(argv: list[str] | None = None) -> int:
    """``seal_packet`` — build a packet from a captures dir + manifest inputs.

    Reads a ``--inputs`` JSON describing the captures (their metadata) and a
    ``--facts`` JSON, signs with ``--key`` (hex private key), writes to
    ``--out``. This is the operator-side tool; Component 2 (BD capture) calls
    the library directly. Kept here so the packet can be (re)sealed from the
    CLI for demos and tests.
    """
    import json

    from amber.packet import CaptureInput, seal_packet

    parser = argparse.ArgumentParser(
        prog="seal_packet",
        description="Seal an Amber evidence packet from captured bodies + facts.",
    )
    parser.add_argument("--captures-dir", required=True, help="dir of <capture_id>.body files")
    parser.add_argument(
        "--inputs",
        required=True,
        help="JSON file: a list of capture metadata objects "
        "(capture_id, url, country, exit_ip, requested_at, http_status, headers)",
    )
    parser.add_argument("--facts", required=True, help="facts.json (Layer-1 deterministic facts)")
    parser.add_argument("--key", required=True, help="hex ed25519 private key (32-byte seed)")
    parser.add_argument("--out", required=True, help="output packet directory")
    args = parser.parse_args(argv)

    inputs = json.loads(Path(args.inputs).read_bytes().decode("utf-8"))
    facts = json.loads(Path(args.facts).read_bytes().decode("utf-8"))
    captures_dir = Path(args.captures_dir)

    pairs = []
    for item in inputs:
        cap = CaptureInput(
            capture_id=item["capture_id"],
            url=item["url"],
            country=item["country"],
            exit_ip=item["exit_ip"],
            requested_at=item["requested_at"],
            http_status=int(item["http_status"]),
            headers=dict(item.get("headers", {})),
        )
        body = (captures_dir / f"{cap.capture_id}.body").read_bytes()
        pairs.append((cap, body))

    out = seal_packet(args.out, pairs, facts, args.key)
    sys.stdout.write(f"seal_packet: sealed {len(pairs)} capture(s) -> {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
