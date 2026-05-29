"""``amber-memory`` CLI — the Cognee agent-memory / temporal-persistence layer.

Subcommands:

  * ``amber-memory ingest <packet_dir> [<packet_dir> ...]`` — read each signed
    packet's ``facts.json`` (read-only), map it to a deterministic observation,
    and ingest the set into the self-hosted Cognee temporal knowledge graph
    (Gemini backend). Ingestion is REAL captures only — no fabricated history.
  * ``amber-memory query "<question>"`` — answer an agent-memory question from
    the Cognee graph (e.g. "has this SKU shown a net-of-tax gap before / is it
    persistent?"). Use ``--temporal`` for time-aware questions.
  * ``amber-memory persistence <packet_dir> [<packet_dir> ...]`` — the
    deterministic persistence answer (transient vs sustained, recurring SKUs,
    the HONEST "N captures over [real window]" framing) computed directly from
    the signed facts. Runs OFFLINE — no Gemini calls, no credits — so it is the
    reproducible ground truth the graph answers can be checked against.
  * ``amber-memory creds`` — secret-free Gemini key state (never prints the key).

The memory artifacts live in Cognee's own store; the signed packet is NEVER
modified (this CLI reads ``facts.json`` and nothing else from the packet).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from amber.memory import config as mcfg
from amber.memory.observations import FactsParseError, Observation, observation_from_packet
from amber.memory.persistence import analyze_recurrence, analyze_sku, group_by_sku


def _load_observations(packet_dirs: list[str]) -> list[Observation]:
    observations: list[Observation] = []
    for d in packet_dirs:
        pkt = Path(d)
        if not pkt.is_dir():
            raise FactsParseError(f"not a directory: {pkt}")
        observations.append(observation_from_packet(pkt))
    return observations


def _ingest(args: argparse.Namespace) -> int:
    try:
        observations = _load_observations(args.packet_dir)
    except FactsParseError as exc:
        sys.stderr.write(f"amber-memory: {exc}\n")
        return 2

    # Fail clearly (not mid-ingest) if no Gemini key is resolvable.
    state = mcfg.describe_key_state()
    if not state["present"]:
        sys.stderr.write(
            "amber-memory: no Gemini API key found (set GEMINI_API_KEY in the env "
            f"or in {mcfg.ENV_FILE}). Ingestion needs the Gemini backend; the "
            "offline 'persistence' subcommand needs no key.\n"
        )
        return 2

    from amber.memory.store import ingest  # lazy: only here do we need cognee

    sys.stdout.write(
        f"amber-memory: ingesting {len(observations)} signed observation(s) into "
        f"the Cognee temporal graph (Gemini backend, key {state['source']})...\n"
    )
    n = ingest(observations, reset=not args.append)
    sys.stdout.write(f"amber-memory: ingested {n} observation(s). Real captures only.\n")
    # Show the honest window so the user never mistakes this for fabricated history.
    for key, obs_list in group_by_sku(observations).items():
        rep = analyze_sku(obs_list)
        sys.stdout.write(f"  SKU {key}: {rep.real_window}\n")
    return 0


def _query(args: argparse.Namespace) -> int:
    state = mcfg.describe_key_state()
    if not state["present"]:
        sys.stderr.write(
            "amber-memory: no Gemini API key found (set GEMINI_API_KEY in the env "
            f"or in {mcfg.ENV_FILE}).\n"
        )
        return 2

    from amber.memory.store import query  # lazy: only here do we need cognee

    search_type = "TEMPORAL" if args.temporal else "GRAPH_COMPLETION"
    answer = query(args.question, search_type=search_type, top_k=args.top_k)
    sys.stdout.write(f"amber-memory query [{answer.search_type}]: {answer.question}\n\n")
    sys.stdout.write(answer.as_text() + "\n")
    return 0


def _persistence(args: argparse.Namespace) -> int:
    try:
        observations = _load_observations(args.packet_dir)
    except FactsParseError as exc:
        sys.stderr.write(f"amber-memory: {exc}\n")
        return 2

    sys.stdout.write(
        "amber-memory persistence (deterministic; offline; no Gemini calls):\n"
    )
    buckets = group_by_sku(observations)
    reports = []
    for key, obs_list in buckets.items():
        rep = analyze_sku(obs_list)
        reports.append(rep)
        sys.stdout.write(f"\n  SKU: {rep.sku_label or key}\n")
        sys.stdout.write(f"    GTIN: {rep.canonical_gtin}\n")
        sys.stdout.write(f"    countries: {', '.join(rep.countries)}\n")
        sys.stdout.write(f"    window: {rep.real_window}\n")
        sys.stdout.write(f"    VERDICT: {rep.verdict}\n")
        sys.stdout.write(
            f"    gap in {rep.captures_with_gap}/{rep.n_captures} captures; "
            f"latest net-of-tax delta {rep.latest_net_of_tax_delta} EUR "
            f"(dearer: {rep.latest_more_expensive_country})\n"
        )
        sys.stdout.write(
            f"    within-country control corroborated every capture: "
            f"{rep.within_country_corroborated}\n"
        )
        sys.stdout.write(f"    rationale: {rep.rationale}\n")

    rec = analyze_recurrence(observations)
    sys.stdout.write(
        f"\n  recurrence: {rec.n_observations} observation(s), "
        f"{rec.n_distinct_skus} distinct SKU(s); "
        f"{len(rec.recurring_skus)} recurring (seen >1 capture).\n"
    )
    if args.json:
        payload = {
            "persistence": [r.as_dict() for r in reports],
            "recurrence": rec.as_dict(),
        }
        sys.stdout.write("\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


def _creds(args: argparse.Namespace) -> int:
    state = mcfg.describe_key_state()
    sys.stdout.write(f"amber-memory: Gemini key present={state['present']} ")
    sys.stdout.write(f"source={state['source']}\n")
    sys.stdout.write(
        f"  LLM model: {mcfg.DEFAULT_CONFIG.llm_model}; "
        f"embedding model: {mcfg.DEFAULT_CONFIG.embedding_model} "
        f"(one Gemini key serves both)\n"
    )
    return 0 if state["present"] else 1


def _force_utf8_stdio() -> None:
    """Render UTF-8 output identically on any console (Windows cp1252 included).

    Our summaries are valid UTF-8 (em dashes, the EUR figures); a legacy console
    code page would otherwise mojibake them. Reconfigure the streams to UTF-8
    rather than dumbing the text down. Best-effort: if a stream cannot be
    reconfigured (already wrapped/redirected), we leave it as-is.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="amber-memory",
        description="Amber agent-memory / temporal-persistence layer (Phase 2): "
        "ingest signed price observations into a self-hosted Cognee temporal "
        "knowledge graph (Gemini backend) and answer persistence questions. "
        "Real captures only — price history is never fabricated.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="ingest signed packet(s) into the Cognee graph")
    p_ing.add_argument("packet_dir", nargs="+", help="path(s) to sealed amber_packet/ dir(s)")
    p_ing.add_argument(
        "--append",
        action="store_true",
        help="add to the existing graph instead of resetting it first",
    )
    p_ing.set_defaults(func=_ingest)

    p_q = sub.add_parser("query", help="answer an agent-memory question from the graph")
    p_q.add_argument("question", help="the natural-language question")
    p_q.add_argument(
        "--temporal",
        action="store_true",
        help="use the time-aware TEMPORAL search (persistence / 'before?' questions)",
    )
    p_q.add_argument("--top-k", type=int, default=10, help="max graph results (default 10)")
    p_q.set_defaults(func=_query)

    p_p = sub.add_parser(
        "persistence",
        help="deterministic persistence answer (offline; no Gemini) from signed facts",
    )
    p_p.add_argument("packet_dir", nargs="+", help="path(s) to sealed amber_packet/ dir(s)")
    p_p.add_argument("--json", action="store_true", help="also print the full JSON report")
    p_p.set_defaults(func=_persistence)

    p_c = sub.add_parser("creds", help="secret-free Gemini key state (never prints the key)")
    p_c.set_defaults(func=_creds)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
