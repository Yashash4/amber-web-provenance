"""Self-hosted Cognee wiring — ingest signed observations, query the graph.

This is the only module that imports ``cognee`` (lazily, like the jury imports
``openai``), so the rest of the memory package + the unit suite import and run
without the package installed and without burning any credits.

What it does:

  * **Configure Cognee on the Gemini backend** — LLM + embeddings both point at
    Gemini's OpenAI-compatible endpoint using the single ``GEMINI_API_KEY``
    (resolved by :mod:`amber.memory.config`; never printed). One key covers both,
    so the memory layer needs no extra credentials and stays inside the free tier.
    Multi-user access control is disabled for the self-hosted single-operator
    case so ingestion runs without an auth dance.
  * **Ingest observations** as a temporal knowledge graph. Each signed packet is
    rendered to a SMALL document (a sentence + the deterministic facts JSON) and
    added to a dataset, then ``cognify(temporal_cognify=True)`` builds the
    knowledge + temporal graph. We ingest only the real captures that exist;
    price history is never fabricated.
  * **Query** the graph for the agent-memory questions (persistence, recurrence)
    via ``search``.

Layer boundary: this reads the signed facts (via the Observation objects) and
writes ONLY into Cognee's own store (under the Cognee data dir) — never into the
signed packet. It does not import the Phase-1 signing core.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from amber.memory.config import (
    DEFAULT_CONFIG,
    MemoryConfig,
    load_gemini_key,
)
from amber.memory.observations import Observation

# The Cognee dataset Amber ingests its observations into.
DATASET_NAME = "amber_price_observations"

# A NodeSet tag so all Amber nodes are grouped + filterable in the graph.
NODE_SET = ["amber_observation"]


def configure_cognee(config: MemoryConfig = DEFAULT_CONFIG, *, gemini_key: str | None = None):
    """Configure self-hosted Cognee to use Gemini for the LLM and embeddings.

    Idempotent. The key is resolved from the env/.env if not supplied and handed
    straight to Cognee; it is never printed or returned. Returns the ``cognee``
    module (lazily imported) so callers can drive it.
    """
    key = gemini_key if gemini_key is not None else load_gemini_key()

    # Self-host: single operator, no multi-tenant auth dance, no telemetry.
    # Set BEFORE importing cognee so the package reads them at import time.
    os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")
    os.environ.setdefault("TELEMETRY_DISABLED", "true")
    # Skip Cognee's LLM preflight: it issues an extra structured-output probe that,
    # on a rate-limited (HTTP 429) free-tier key, backs off PAST its 30s timeout and
    # blocks the real pipeline. The actual ingest/query calls below exercise the LLM
    # for real — the preflight adds nothing but a failure mode under rate limits.
    os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")

    import cognee  # lazy import: keeps the dep optional for the unit suite

    # LLM: native Gemini via LiteLLM (the ``gemini/`` model namespace resolves
    # Google's endpoint itself, so no custom endpoint — overriding it makes the
    # connection test hang). The single Gemini key authenticates the call.
    llm_cfg = {
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "llm_api_key": key,
    }
    if config.llm_endpoint:
        llm_cfg["llm_endpoint"] = config.llm_endpoint
    cognee.config.set_llm_config(llm_cfg)

    # Embeddings: the SAME Gemini key + native provider (one key, no extra creds).
    emb_cfg = {
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "embedding_dimensions": config.embedding_dimensions,
        # Cognee's embedding-config field is ``embedding_max_completion_tokens``
        # (it caps the per-call token budget); gemini-embedding-001 accepts 2048.
        "embedding_max_completion_tokens": config.embedding_max_tokens,
        "embedding_api_key": key,
    }
    if config.embedding_endpoint:
        emb_cfg["embedding_endpoint"] = config.embedding_endpoint
    cognee.config.set_embedding_config(emb_cfg)
    return cognee


def observation_to_document(obs: Observation) -> str:
    """Render ONE signed observation to a small ingestion document.

    A short natural-language sentence (so the graph extracts entities + the
    temporal anchor) followed by the deterministic facts as compact JSON. Kept
    SMALL — one observation, a handful of fields — so ingestion stays inside the
    Gemini free tier. Every figure here was computed deterministically by the
    Component-2 floor and sealed in the Merkle-signed facts; no number is invented
    and no price history is fabricated.
    """
    sku = obs.sku_label or obs.canonical_gtin or obs.packet_id
    when = obs.observed_at or "an unrecorded instant"
    if obs.net_of_tax_delta and obs.delta_is_nonzero:
        gap_sentence = (
            f"On {when}, the SKU '{sku}' (GTIN {obs.canonical_gtin}) showed a "
            f"net-of-tax price gap of {obs.net_of_tax_delta} EUR between "
            f"{'/'.join(obs.countries)}: {obs.more_expensive_country} was the more "
            f"expensive market (net {obs.more_expensive_net}) versus "
            f"{obs.cheaper_country} (net {obs.cheaper_net}). "
        )
    else:
        gap_sentence = (
            f"On {when}, the SKU '{sku}' (GTIN {obs.canonical_gtin}) showed no "
            f"net-of-tax price gap between {'/'.join(obs.countries)}. "
        )
    control_sentence = (
        "The within-country control "
        + ("agreed (the gap survived multiple distinct in-country residential "
           "exits, so it is a controlled experiment, not exit-IP noise). "
           if obs.within_country_all_agree
           else "did not uniformly agree. ")
    )
    facts = {
        "packet_id": obs.packet_id,
        "observed_at": obs.observed_at,
        "sku_label": obs.sku_label,
        "canonical_gtin": obs.canonical_gtin,
        "countries": list(obs.countries),
        "primary_finding": obs.primary_finding,
        "net_of_tax_delta_eur": obs.net_of_tax_delta,
        "more_expensive_country": obs.more_expensive_country,
        "cheaper_country": obs.cheaper_country,
        "delta_is_nonzero": obs.delta_is_nonzero,
        "within_country_all_agree": obs.within_country_all_agree,
        "dispatched_same_second": obs.dispatched_same_second,
    }
    return (
        gap_sentence
        + control_sentence
        + "Deterministic signed facts: "
        + json.dumps(facts, sort_keys=True, ensure_ascii=False)
    )


async def _ingest_async(observations: list[Observation], cognee, *, reset: bool) -> int:
    if reset:
        # Start clean so a re-ingest is reproducible (prune the prior graph/data).
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(metadata=True)
    for obs in observations:
        await cognee.add(
            observation_to_document(obs),
            dataset_name=DATASET_NAME,
            node_set=NODE_SET,
        )
    # Build the knowledge + TEMPORAL graph over the ingested observations.
    await cognee.cognify(datasets=[DATASET_NAME], temporal_cognify=True)
    return len(observations)


def ingest(
    observations: list[Observation],
    *,
    config: MemoryConfig = DEFAULT_CONFIG,
    gemini_key: str | None = None,
    reset: bool = True,
) -> int:
    """Ingest signed observations into the self-hosted Cognee temporal graph.

    Configures the Gemini backend, then adds each observation document and runs
    ``cognify(temporal_cognify=True)``. Returns the number of observations
    ingested. Synchronous wrapper around Cognee's async API (drives its own event
    loop). Never fabricates an observation — it ingests exactly what it is given.
    """
    if not observations:
        raise ValueError("ingest requires at least one observation")
    cognee = configure_cognee(config, gemini_key=gemini_key)
    return asyncio.run(_ingest_async(observations, cognee, reset=reset))


@dataclass(frozen=True)
class GraphAnswer:
    """A query answer from the Cognee graph (the agent-memory surface)."""

    question: str
    search_type: str
    results: list[Any]

    def as_text(self) -> str:
        parts = []
        for r in self.results:
            parts.append(r if isinstance(r, str) else json.dumps(r, default=str))
        return "\n".join(parts) if parts else "(no graph results)"


async def _query_async(question: str, cognee, *, search_type_name: str, top_k: int):
    search_type = getattr(cognee.SearchType, search_type_name)
    return await cognee.search(
        query_text=question,
        query_type=search_type,
        datasets=[DATASET_NAME],
        top_k=top_k,
    )


def query(
    question: str,
    *,
    config: MemoryConfig = DEFAULT_CONFIG,
    gemini_key: str | None = None,
    search_type: str = "GRAPH_COMPLETION",
    top_k: int = 10,
) -> GraphAnswer:
    """Answer an agent-memory question from the Cognee graph.

    ``search_type`` is a ``cognee.SearchType`` name — ``GRAPH_COMPLETION`` for a
    grounded natural-language answer, ``TEMPORAL`` for time-aware questions
    ("has this gap appeared before / is it persistent"). Configures the Gemini
    backend and runs the search. The graph must have been ``ingest``-ed first.
    """
    cognee = configure_cognee(config, gemini_key=gemini_key)
    results = asyncio.run(
        _query_async(question, cognee, search_type_name=search_type, top_k=top_k)
    )
    return GraphAnswer(question=question, search_type=search_type, results=list(results))
