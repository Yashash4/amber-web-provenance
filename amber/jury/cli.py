"""``amber-jury`` CLI — the Layer-2 legal-jury advisory (Phase 2, standalone).

Two subcommands:

  * ``amber-jury classify <packet_dir>`` — read the packet's ``facts.json``, run
    the three-model jury, print the advisory (the three model labels + the
    consensus / route-to-human verdict), and write ``legal_advisory.json``
    NEXT TO the packet directory (a SIBLING file — never inside the signed
    packet, per LOCK 4).
  * ``amber-jury goldset`` — run the methodology gold set and print per-model +
    consensus precision / recall / accuracy (the AI/ML-prize evidence).

This CLI is intentionally NOT wired into the Phase-1 demo. It is a standalone
Phase-2 instrument and never modifies the signed Layer-1 packet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from amber.jury import taxonomy
from amber.jury.goldset import evaluate_goldset
from amber.jury.jury import Advisory, run_jury

# The advisory is written as a SIBLING of the packet dir, never inside it.
ADVISORY_FILENAME = "legal_advisory.json"


def _advisory_sibling_path(packet_dir: Path) -> Path:
    """Path for the advisory file: a sibling of the packet dir.

    For ``.../samples/floor_demo_packet`` the advisory is
    ``.../samples/floor_demo_packet.legal_advisory.json`` — physically outside
    the signed packet directory so it can never be mistaken for sealed content.
    """
    return packet_dir.parent / f"{packet_dir.name}.{ADVISORY_FILENAME}"


def _print_advisory(advisory: Advisory, stream) -> None:
    stream.write("amber-jury: Layer-2 legal advisory (UNSIGNED — NOT legal advice)\n")
    stream.write(f"  schema: {advisory.schema}\n")
    stream.write("  jurors:\n")
    for j in advisory.jurors:
        status = "ok" if j.ok else f"ERROR ({j.error})"
        stream.write(f"    - {j.family:<10} {j.model_id:<32} -> {j.label}  [{status}]\n")
        stream.write(f"        rationale: {j.rationale}\n")
    stream.write(f"  tally: {json.dumps(advisory.tally, sort_keys=True)}\n")
    if advisory.routed_to_human:
        stream.write("  >> NO MAJORITY -> ROUTE_TO_HUMAN (the jury never auto-resolves a split)\n")
    else:
        stream.write(f"  >> CONSENSUS (majority): {advisory.advisory_label}\n")
        stream.write(f"     criterion: {advisory.criterion}\n")
    stream.write(f"\n  {advisory.disclaimer}\n")


def _classify(args: argparse.Namespace) -> int:
    packet_dir = Path(args.packet_dir)
    if not packet_dir.is_dir():
        sys.stderr.write(f"amber-jury: not a directory: {packet_dir}\n")
        return 2
    facts_path = packet_dir / "facts.json"
    if not facts_path.exists():
        sys.stderr.write(f"amber-jury: no facts.json in {packet_dir}\n")
        return 2

    facts = json.loads(facts_path.read_bytes().decode("utf-8"))
    advisory = run_jury(facts)
    _print_advisory(advisory, sys.stdout)

    out_path = _advisory_sibling_path(packet_dir)
    out_path.write_text(
        json.dumps(advisory.as_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    sys.stdout.write(f"\n  advisory written (UNSIGNED, sibling of packet): {out_path}\n")
    # Defensive guarantee: confirm we did NOT write into the signed packet.
    inside = packet_dir / ADVISORY_FILENAME
    if inside.exists():
        sys.stderr.write(
            "amber-jury: FATAL — an advisory file appeared INSIDE the signed "
            f"packet ({inside}); refusing (LOCK 4 violation).\n"
        )
        return 3
    return 0


def _goldset(args: argparse.Namespace) -> int:
    report = evaluate_goldset()
    sys.stdout.write(f"amber-jury goldset: {report.version}\n")
    sys.stdout.write(f"  examples: {report.n_examples}\n\n")

    def line(m) -> None:
        sys.stdout.write(
            f"  {m.name:<11} acc={m.accuracy:.3f}  "
            f"macro_P={m.macro_precision:.3f}  macro_R={m.macro_recall:.3f}  "
            f"macro_F1={m.macro_f1:.3f}  ({m.correct}/{m.n})\n"
        )

    sys.stdout.write("  per-model + consensus (macro = mean over labels present):\n")
    for name in ("openai", "google", "anthropic"):
        line(report.per_model[name])
    line(report.consensus)

    if args.json:
        sys.stdout.write("\n")
        sys.stdout.write(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amber-jury",
        description="Amber Layer-2 legal jury (Phase 2): three independent "
        "models classify a signed Layer-1 observation against Reg (EU) "
        "2018/302. Output is an UNSIGNED advisory, never written into the "
        "signed packet.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_classify = sub.add_parser(
        "classify",
        help="classify a packet's facts.json; write legal_advisory.json beside it",
    )
    p_classify.add_argument("packet_dir", help="path to a sealed amber_packet/ directory")
    p_classify.set_defaults(func=_classify)

    p_gold = sub.add_parser(
        "goldset",
        help="run the methodology gold set; print precision/recall/accuracy",
    )
    p_gold.add_argument(
        "--json", action="store_true", help="also print the full JSON report"
    )
    p_gold.set_defaults(func=_goldset)

    args = parser.parse_args(argv)
    # Touch the taxonomy module so a packaging error surfaces early/clearly.
    _ = taxonomy.LABEL_TOKENS
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
