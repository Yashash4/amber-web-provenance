"""The Amber -> TriggerWare event-driven workflow orchestration.

Ties one signed Amber observation to TriggerWare's trigger primitive:

  1. ARM   — read a sealed packet's signed Layer-1 facts, derive the event
             (deterministic, thresholded), and register a TriggerWare trigger
             whose saved SQL fires exactly when the signed net-of-tax delta
             exceeds the brand's threshold (or an access/payment denial exists).
  2. QUERY — expose the event as a TriggerWare queryable API row (``POST /query``)
             a brand-protection agent can read on demand.
  3. POLL  — poll the trigger for the accumulated delta; a fired trigger is the
             event-driven signal that drives an ACTION / ALERT.
  4. ACT   — render the action: a structured brand-protection alert stating the
             signed FACT (never a "violation" verdict).

LAYER BOUNDARY: every value flows OUT of the signed facts; nothing flows back
in. This module never imports or mutates the Phase-1 packet/capture spine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from amber.workflow.client import (
    Trigger,
    TriggerDelta,
    TriggerWareClient,
)
from amber.workflow.event import (
    AmberEvent,
    EventThreshold,
    extract_event,
    load_facts,
)
from amber.workflow.sql import build_query_sql, build_trigger_sql

# Default poll cadence for a registered trigger (seconds). The brand's recurring
# SaaS monitors a watched SKU on this cadence.
DEFAULT_SCHEDULE_S = 300

# TriggerWare trigger names: lowercase alnum + underscore.
_NAME_SAFE = re.compile(r"[^a-z0-9_]+")


def trigger_name_for(sku_label: str, *, prefix: str = "amber") -> str:
    """A deterministic, API-safe trigger name from the SKU label.

    Same SKU -> same trigger name, so re-arming a watched SKU updates rather than
    proliferates triggers (the caller decides update-vs-create).
    """
    slug = _NAME_SAFE.sub("_", sku_label.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)[:48] or "sku"
    return f"{prefix}_{slug}"


@dataclass
class ArmResult:
    """The outcome of arming a watched SKU as a TriggerWare trigger."""

    event: AmberEvent
    trigger: Trigger
    query_sql: str
    trigger_sql: str
    created: bool  # True if newly created, False if an existing trigger was updated

    def summary(self) -> dict[str, Any]:
        return {
            "trigger_name": self.trigger.name,
            "schedule_s": self.trigger.schedule,
            "status": self.trigger.status,
            "created": self.created,
            "event": self.event.as_dict(),
            "trigger_sql": self.trigger_sql,
        }


@dataclass
class Alert:
    """A brand-protection action rendered from a fired trigger.

    States the signed FACT and the provenance context; it is NOT a legal verdict
    and carries no "violation" language. A downstream system (email, ticket,
    webhook) consumes this structured alert.
    """

    sku_label: str
    kind: str
    fact_banner: str
    detail: dict[str, Any]
    raised_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "amber/workflow_alert@1",
            "sku_label": self.sku_label,
            "kind": self.kind,
            "fact_banner": self.fact_banner,
            "detail": self.detail,
            "raised_at": self.raised_at,
            "note": (
                "Action driven by a fired TriggerWare trigger over Amber's "
                "signed Layer-1 facts. States a FACT, not a legal verdict; any "
                "legal characterisation is a separate unsigned Layer-2 advisory."
            ),
        }

    def render_text(self) -> str:
        lines = [
            "── AMBER BRAND-PROTECTION ALERT ──────────────────────────────",
            f"  SKU:    {self.sku_label}",
            f"  Event:  {self.kind}",
            f"  Fact:   {self.fact_banner}",
        ]
        for k, v in self.detail.items():
            lines.append(f"  {k}: {v}")
        lines.append(f"  Raised: {self.raised_at}")
        lines.append("  (signed FACT — not a legal verdict; counsel confirms any characterisation)")
        return "\n".join(lines)


def _existing_trigger(client: TriggerWareClient, name: str) -> Trigger | None:
    for t in client.list_triggers():
        if t.name == name:
            return t
    return None


def arm_from_packet(
    packet_dir: Path | str,
    client: TriggerWareClient,
    *,
    threshold: EventThreshold | None = None,
    schedule_s: int = DEFAULT_SCHEDULE_S,
    name_prefix: str = "amber",
) -> ArmResult:
    """Derive the event from a signed packet and register/update its trigger.

    Raises :class:`amber.workflow.event.NoEventError` (propagated) when the
    signed facts hold no above-threshold event — Amber never arms a trigger for
    a finding that does not exist.
    """
    facts = load_facts(packet_dir)
    threshold = threshold or EventThreshold()
    event = extract_event(facts, threshold)

    query_sql = build_query_sql(event)
    trigger_sql = build_trigger_sql(event, threshold.net_delta_eur)
    name = trigger_name_for(event.sku_label, prefix=name_prefix)

    existing = _existing_trigger(client, name)
    if existing is not None:
        trigger = client.update_trigger(
            name, query=trigger_sql, schedule=schedule_s, status="enabled"
        )
        created = False
    else:
        trigger = client.create_trigger(name, trigger_sql, schedule=schedule_s)
        created = True

    return ArmResult(
        event=event,
        trigger=trigger,
        query_sql=query_sql,
        trigger_sql=trigger_sql,
        created=created,
    )


def run_query_api(
    packet_dir: Path | str,
    client: TriggerWareClient,
    *,
    threshold: EventThreshold | None = None,
) -> list[dict[str, Any]]:
    """Expose the signed observation as a TriggerWare queryable API row.

    Runs the event's SELECT through ``POST /query`` and returns the rows as
    name->value records (what a brand-protection agent would read on demand).
    Uses the compact signal-column projection: TriggerWare's SQL engine starts
    timing out past ~13 columns (confirmed live), so the verbose prose columns
    (fact_banner / sku_label) are kept on the locally-rendered alert, not the
    served row — the agent gets every machine-readable signal it needs.
    """
    facts = load_facts(packet_dir)
    event = extract_event(facts, threshold or EventThreshold())
    result = client.query(build_query_sql(event, restrict_to_signal=True), language="sql")
    return result.as_records()


def poll_for_event(client: TriggerWareClient, trigger_name: str) -> TriggerDelta:
    """Poll a registered trigger; the returned delta is the event-driven signal."""
    return client.poll_trigger(trigger_name)


def alert_from_event(event: AmberEvent) -> Alert:
    """Render the brand-protection action from the (fired) event's signed facts."""
    if event.kind == "NET_OF_TAX_PRICE_DELTA":
        detail = {
            "net_of_tax_delta_eur": (
                format(event.net_of_tax_delta_eur, "f")
                if event.net_of_tax_delta_eur is not None
                else None
            ),
            "more_expensive_country": event.more_expensive_country,
            "cheaper_country": event.cheaper_country,
            "threshold_eur": format(event.threshold_eur, "f"),
            "within_country_control_agree": event.within_country_control_agree,
            "sku_identity_confidence": event.sku_identity_confidence,
            "dispatched_same_second": event.dispatched_same_second,
        }
    else:
        detail = {
            "geo_blocked_countries": ",".join(event.geo_blocked_countries) or None,
            "purchasable_countries": ",".join(event.purchasable_countries) or None,
            "sku_identity_confidence": event.sku_identity_confidence,
        }
    return Alert(
        sku_label=event.sku_label,
        kind=event.kind,
        fact_banner=event.fact_banner,
        detail=detail,
        raised_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def arm_and_verify(
    packet_dir: Path | str,
    client: TriggerWareClient,
    *,
    threshold: EventThreshold | None = None,
    schedule_s: int = DEFAULT_SCHEDULE_S,
    name_prefix: str = "amber",
) -> tuple[ArmResult, TriggerDelta, Alert | None]:
    """Arm the trigger, then poll it once to confirm it FIRES on the signed delta.

    Returns the arm result, the first poll's delta, and the rendered alert when
    the trigger fired. This is the end-to-end demo path: arm -> the trigger's
    SQL yields the event row -> the first poll reports it as an ``added`` delta
    -> Amber raises the brand-protection alert.
    """
    armed = arm_from_packet(
        packet_dir,
        client,
        threshold=threshold,
        schedule_s=schedule_s,
        name_prefix=name_prefix,
    )
    delta = client.poll_trigger(armed.trigger.name)
    alert = alert_from_event(armed.event) if delta.fired else None
    return armed, delta, alert
