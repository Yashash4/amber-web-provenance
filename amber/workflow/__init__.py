"""Amber Phase-2 — TriggerWare.ai automated-workflow integration (ISOLATED).

The textbook event-driven workflow:

    a signed Amber web-data change  ->  a TriggerWare trigger / queryable API
        ->  an agent decision (poll the delta)  ->  a real-world action / alert.

Concretely: when an Amber capture detects a **net-of-tax price delta above a
threshold** (or an access/payment-denial signal) on a watched SKU, this module
exposes that signed observation as a TriggerWare queryable API row and registers
a TriggerWare **trigger** (a saved SQL query + poll schedule) that fires when the
delta crosses the threshold. A brand-protection agent polls the trigger for the
delta and drives an alert / action.

LAYER BOUNDARY (LOCK 4, non-negotiable): this module only *reads* a signed
Layer-1 ``facts.json``. It never writes into the signed evidence packet, never
imports the Phase-1 packet/capture spine, and never lets an LLM (or this module)
compute a number into the signed bundle. The event it emits is derived purely
from the deterministic, already-signed Layer-1 facts.

This is a Phase-2 module. It is isolated from the Phase-1 spine, the AI/ML jury
(``amber/jury/``), and the Cognee memory module (``amber/memory/``).
"""

from amber.workflow.event import (
    AmberEvent,
    EventThreshold,
    NoEventError,
    extract_event,
    load_facts,
)

__all__ = [
    "AmberEvent",
    "EventThreshold",
    "NoEventError",
    "extract_event",
    "load_facts",
]
