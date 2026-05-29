"""``amber-workflow`` CLI — the Amber -> TriggerWare event-driven workflow.

Subcommands:

  * ``amber-workflow event <packet_dir>``  — OFFLINE: print the deterministic
        event derived from the signed facts (no network, no key needed).
  * ``amber-workflow arm <packet_dir>``    — register a TriggerWare trigger from
        a signed capture, then poll it once to confirm it FIRES on the signed
        delta, and render the brand-protection alert. (LIVE: needs the key.)
  * ``amber-workflow query <packet_dir>``  — expose the signed observation as a
        TriggerWare queryable API row (``POST /query``). (LIVE.)
  * ``amber-workflow poll <trigger_name>`` — poll a registered trigger for its
        accumulated delta. (LIVE.)
  * ``amber-workflow list``                — list registered triggers. (LIVE.)
  * ``amber-workflow disarm <name>``       — delete a trigger. (LIVE.)
  * ``amber-workflow creds``               — report (secret-free) whether a
        TriggerWare key is resolvable. (no network.)

The Phase-1 signed packet is never modified by any subcommand.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import InvalidOperation
from pathlib import Path

from amber.workflow import client as tw_client
from amber.workflow.event import EventThreshold, NoEventError, extract_event, load_facts
from amber.workflow.sql import build_query_sql, build_trigger_sql
from amber.workflow.workflow import (
    DEFAULT_SCHEDULE_S,
    arm_and_verify,
    poll_for_event,
    run_query_api,
)


def _threshold(args: argparse.Namespace) -> EventThreshold:
    try:
        return EventThreshold.from_eur(args.threshold)
    except (InvalidOperation, ValueError) as exc:
        raise SystemExit(
            f"amber-workflow: bad --threshold {args.threshold!r}: {exc}"
        ) from exc


def _make_client() -> tw_client.TriggerWareClient:
    try:
        return tw_client.TriggerWareClient()
    except tw_client.APIKeyMissing as exc:
        sys.stderr.write(f"amber-workflow: {exc}\n")
        raise SystemExit(2) from exc


def _event_offline(args: argparse.Namespace) -> int:
    """Print the deterministic event from the signed facts (no network)."""
    try:
        facts = load_facts(Path(args.packet_dir))
        event = extract_event(facts, _threshold(args))
    except NoEventError as exc:
        sys.stdout.write(f"amber-workflow: no event — {exc}\n")
        return 1
    sys.stdout.write("amber-workflow event (from signed Layer-1 facts):\n")
    sys.stdout.write(json.dumps(event.as_dict(), indent=2, sort_keys=True))
    sys.stdout.write("\n\n  query SQL (the queryable API row):\n")
    sys.stdout.write(f"    {build_query_sql(event)}\n")
    sys.stdout.write("  trigger SQL (fires when the signed delta exceeds the threshold):\n")
    sys.stdout.write(f"    {build_trigger_sql(event, event.threshold_eur)}\n")
    return 0


def _arm(args: argparse.Namespace) -> int:
    try:
        facts_ok = load_facts(Path(args.packet_dir))  # fail fast w/o a network call
        _ = facts_ok
    except NoEventError as exc:
        sys.stderr.write(f"amber-workflow: {exc}\n")
        return 2
    client = _make_client()
    try:
        armed, delta, alert = arm_and_verify(
            Path(args.packet_dir),
            client,
            threshold=_threshold(args),
            schedule_s=args.schedule,
        )
    except NoEventError as exc:
        sys.stdout.write(f"amber-workflow: no event to arm — {exc}\n")
        return 1
    except tw_client.TriggerWareError as exc:
        sys.stderr.write(f"amber-workflow: TriggerWare API error — {exc} (detail: {exc.detail})\n")
        return 3
    finally:
        client.close()

    verb = "created" if armed.created else "updated"
    sys.stdout.write(
        f"amber-workflow: {verb} TriggerWare trigger '{armed.trigger.name}' "
        f"(schedule {armed.trigger.schedule}s, status {armed.trigger.status})\n"
    )
    sys.stdout.write(f"  trigger SQL: {armed.trigger_sql}\n")
    sys.stdout.write(
        f"  poll result: added={len(delta.added)} deleted={len(delta.deleted)} "
        f"fired={delta.fired}\n"
    )
    if alert is not None:
        sys.stdout.write("\n" + alert.render_text() + "\n")
        return 0
    sys.stdout.write(
        "\namber-workflow: trigger armed but did NOT fire on first poll — the "
        "signed facts did not cross the threshold (no event raised).\n"
    )
    return 1


def _query(args: argparse.Namespace) -> int:
    client = _make_client()
    try:
        records = run_query_api(Path(args.packet_dir), client, threshold=_threshold(args))
    except NoEventError as exc:
        sys.stdout.write(f"amber-workflow: no event — {exc}\n")
        return 1
    except tw_client.TriggerWareError as exc:
        sys.stderr.write(f"amber-workflow: TriggerWare API error — {exc} (detail: {exc.detail})\n")
        return 3
    finally:
        client.close()
    sys.stdout.write("amber-workflow: TriggerWare queryable API row(s):\n")
    sys.stdout.write(json.dumps(records, indent=2, sort_keys=True, default=str))
    sys.stdout.write("\n")
    return 0


def _poll(args: argparse.Namespace) -> int:
    client = _make_client()
    try:
        delta = poll_for_event(client, args.trigger_name)
    except tw_client.TriggerWareError as exc:
        sys.stderr.write(f"amber-workflow: TriggerWare API error — {exc} (detail: {exc.detail})\n")
        return 3
    finally:
        client.close()
    sys.stdout.write(
        json.dumps(
            {"added": delta.added, "deleted": delta.deleted, "fired": delta.fired},
            indent=2,
            default=str,
        )
    )
    sys.stdout.write("\n")
    return 0


def _list(args: argparse.Namespace) -> int:
    client = _make_client()
    try:
        triggers = client.list_triggers()
    except tw_client.TriggerWareError as exc:
        sys.stderr.write(f"amber-workflow: TriggerWare API error — {exc} (detail: {exc.detail})\n")
        return 3
    finally:
        client.close()
    sys.stdout.write(
        json.dumps(
            [
                {"name": t.name, "schedule": t.schedule, "status": t.status, "query": t.query}
                for t in triggers
            ],
            indent=2,
        )
    )
    sys.stdout.write("\n")
    return 0


def _disarm(args: argparse.Namespace) -> int:
    client = _make_client()
    try:
        client.delete_trigger(args.trigger_name)
    except tw_client.TriggerWareError as exc:
        sys.stderr.write(f"amber-workflow: TriggerWare API error — {exc} (detail: {exc.detail})\n")
        return 3
    finally:
        client.close()
    sys.stdout.write(f"amber-workflow: deleted trigger '{args.trigger_name}'\n")
    return 0


def _creds(args: argparse.Namespace) -> int:
    state = tw_client.describe_key_state()
    sys.stdout.write(json.dumps(state) + "\n")
    if not state["present"]:
        sys.stdout.write(
            "amber-workflow: no TriggerWare key — set TRIGGERWARE_API_KEY in the "
            "env or code/.env. (No key is ever printed.)\n"
        )
        return 1
    return 0


def _add_threshold_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--threshold",
        default="1.00",
        help="net-of-tax delta (EUR) above which a price delta is an event "
        "(the brand's alert knob; default 1.00). Not a legal number.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amber-workflow",
        description="Amber -> TriggerWare.ai event-driven workflow (Phase 2): a "
        "signed web-data change becomes a TriggerWare trigger that drives a "
        "brand-protection alert. Never modifies the signed packet.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_event = sub.add_parser("event", help="OFFLINE: print the event from signed facts")
    p_event.add_argument("packet_dir", help="path to a sealed amber packet directory")
    _add_threshold_arg(p_event)
    p_event.set_defaults(func=_event_offline)

    p_arm = sub.add_parser("arm", help="register a TriggerWare trigger and verify it fires")
    p_arm.add_argument("packet_dir", help="path to a sealed amber packet directory")
    p_arm.add_argument(
        "--schedule", type=int, default=DEFAULT_SCHEDULE_S, help="poll cadence (seconds)"
    )
    _add_threshold_arg(p_arm)
    p_arm.set_defaults(func=_arm)

    p_query = sub.add_parser("query", help="expose the observation as a queryable API row")
    p_query.add_argument("packet_dir", help="path to a sealed amber packet directory")
    _add_threshold_arg(p_query)
    p_query.set_defaults(func=_query)

    p_poll = sub.add_parser("poll", help="poll a trigger for its accumulated delta")
    p_poll.add_argument("trigger_name", help="the registered trigger name")
    p_poll.set_defaults(func=_poll)

    p_list = sub.add_parser("list", help="list registered triggers")
    p_list.set_defaults(func=_list)

    p_disarm = sub.add_parser("disarm", help="delete a registered trigger")
    p_disarm.add_argument("trigger_name", help="the registered trigger name")
    p_disarm.set_defaults(func=_disarm)

    p_creds = sub.add_parser("creds", help="report (secret-free) whether a key is set")
    p_creds.set_defaults(func=_creds)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
