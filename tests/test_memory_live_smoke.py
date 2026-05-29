"""ONE guarded live smoke test against self-hosted Cognee on the real Gemini key.

Skipped by default so the suite never burns the Gemini free tier. Enable with::

    AMBER_MEMORY_LIVE=1 pytest tests/test_memory_live_smoke.py -q

It ingests the SINGLE real AirPods packet into a self-hosted Cognee temporal
graph (Gemini backend) and runs ONE query, confirming end-to-end wiring (key
resolution -> Gemini LLM + embeddings -> add -> temporal cognify -> search). It
asserts only that ingestion ran and the query returned a non-empty answer — never
fabricates data, and keeps the call count minimal.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from amber.memory.config import GeminiKeyMissing, load_gemini_key

LIVE = os.environ.get("AMBER_MEMORY_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="live Cognee/Gemini smoke test; set AMBER_MEMORY_LIVE=1 to run",
)

LIVE_PACKET = Path(__file__).resolve().parent.parent / "samples" / "live_packet"


def test_live_ingest_and_query():
    try:
        load_gemini_key()
    except GeminiKeyMissing:
        pytest.skip("no Gemini key available for the live smoke test")

    from amber.memory.observations import observation_from_packet
    from amber.memory.store import ingest, query

    obs = observation_from_packet(LIVE_PACKET)
    n = ingest([obs], reset=True)  # real Gemini calls; tiny (one observation)
    assert n == 1

    answer = query(
        "Has the Apple AirPods 4 SKU shown a net-of-tax price gap between "
        "Germany and Belgium, and how many times has it been observed?",
        search_type="TEMPORAL",
    )
    text = answer.as_text()
    assert text and text != "(no graph results)"
