"""Amber Phase-2 module — the Cognee agent-memory / temporal-persistence layer.

This package is an ISOLATED Phase-2 add-on. It reads already-signed Layer-1
``facts.json`` packets and builds an agent **memory** over them — a knowledge +
temporal graph (self-hosted `Cognee`) plus a deterministic persistence analysis —
so an agent can answer questions like *"has this SKU shown a net-of-tax gap
before, and is it persistent?"*.

Layer boundary (LOCK 4 — physical, not rhetorical). This module **reads** the
signed facts and emits a SEPARATE Layer-2-style memory artifact. It NEVER writes
into the signed packet, never imports the Phase-1 signing core
(``amber.packet`` / ``amber.cli`` / ``amber.signer`` / ``amber.merkle`` /
``amber.verifier`` / the ``amber.capture`` floor), and an LLM never computes a
fact or number into the signed bundle. The memory graph is downstream analysis
*over* the signed facts.

Honesty (GROUNDING). Price *history* is NEVER fabricated. The persistence
analysis is computed only over the captures that genuinely exist, and every
human-facing summary frames the window honestly as **"N captures over [real
window]; the baseline compounds from day one"** — never an invented multi-week
chart. With a single capture, the module says so plainly (a one-point baseline,
not a trend).

The Cognee LLM backend is configured against the **direct Gemini API key**
(``GEMINI_API_KEY``); the key is never printed, logged, or placed in any returned
object.
"""

from __future__ import annotations

__all__ = [
    "config",
    "observations",
    "persistence",
    "store",
    "cli",
]
