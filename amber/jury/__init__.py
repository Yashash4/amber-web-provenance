"""Amber Phase-2 module — the three-model legal jury (Layer-2, UNSIGNED).

This package is an ISOLATED Phase-2 add-on. It reads an already-signed Layer-1
``facts.json`` and produces a SEPARATE, clearly-labeled, **unsigned** legal
advisory. It NEVER imports from, or writes into, the Phase-1 signed-packet core
(``amber.packet`` / ``amber.cli`` / the ``amber.capture`` floor). Per LOCK 4 the
Layer-1 / Layer-2 split is physical: an LLM never computes a fact or number into
the signed bundle.

Three causally-different model families (OpenAI / Google / Anthropic, via the
AI/ML API gateway) independently classify the Reg (EU) 2018/302 legal taxonomy;
a strict majority is the advisory, and any split routes to a human. The AI/ML
prize is won with reproducible gold-set precision/recall (``goldset``), NOT with
on-screen consensus theater (LOCK 6 — no Fleiss' kappa on any user surface).
"""

from __future__ import annotations

__all__ = [
    "taxonomy",
    "client",
    "jury",
    "goldset",
    "cli",
]
