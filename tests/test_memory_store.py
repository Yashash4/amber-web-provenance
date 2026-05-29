"""Tests for the Cognee wiring — with Cognee MOCKED (no network, no credits).

A fake ``cognee`` module is injected into ``sys.modules`` so the lazy
``import cognee`` inside the store picks it up. The tests assert:

  * configure wires Gemini for BOTH the LLM and embeddings, with the key passed
    straight through and NEVER printed/returned;
  * ingest renders each observation to a small document and calls add + cognify
    (temporal) with the real captures only — nothing fabricated;
  * query routes to the requested SearchType;
  * the boundary holds — ingest/query never write into the signed packet dir.
"""

from __future__ import annotations

import shutil
import sys
import types
from pathlib import Path

import pytest

from amber.memory import store
from amber.memory.observations import observation_from_packet

LIVE_PACKET = Path(__file__).resolve().parent.parent / "samples" / "live_packet"
SECRET = "AIza-super-secret-gemini-key-DO-NOT-LEAK"


class _FakeConfig:
    def __init__(self):
        self.llm: dict = {}
        self.embedding: dict = {}

    def set_llm_config(self, cfg):
        self.llm = dict(cfg)

    def set_embedding_config(self, cfg):
        self.embedding = dict(cfg)


class _FakePrune:
    def __init__(self, calls):
        self._calls = calls

    async def prune_data(self):
        self._calls.append(("prune_data",))

    async def prune_system(self, metadata=True):
        self._calls.append(("prune_system", metadata))


class _FakeSearchType:
    GRAPH_COMPLETION = "GRAPH_COMPLETION"
    TEMPORAL = "TEMPORAL"


def _make_fake_cognee():
    """Build a fake cognee module recording every call it receives."""
    calls: list = []
    mod = types.ModuleType("cognee")
    mod.config = _FakeConfig()
    mod.prune = _FakePrune(calls)
    mod.SearchType = _FakeSearchType
    mod._calls = calls

    async def add(data, dataset_name=None, node_set=None):
        calls.append(("add", data, dataset_name, tuple(node_set or ())))

    async def cognify(datasets=None, temporal_cognify=False):
        calls.append(("cognify", tuple(datasets or ()), temporal_cognify))

    async def search(query_text, query_type=None, datasets=None, top_k=10):
        calls.append(("search", query_text, query_type, tuple(datasets or ()), top_k))
        return [f"answer to: {query_text}"]

    mod.add = add
    mod.cognify = cognify
    mod.search = search
    return mod


@pytest.fixture
def fake_cognee(monkeypatch):
    mod = _make_fake_cognee()
    monkeypatch.setitem(sys.modules, "cognee", mod)
    # Don't require a real key; pass the secret explicitly to configure/ingest.
    return mod


def test_configure_wires_gemini_for_llm_and_embeddings(fake_cognee):
    cognee = store.configure_cognee(gemini_key=SECRET)
    assert cognee is fake_cognee
    # LLM points at Gemini with the key passed through.
    assert cognee.config.llm["llm_provider"] == "gemini"
    assert cognee.config.llm["llm_model"].startswith("gemini/")
    assert cognee.config.llm["llm_api_key"] == SECRET
    # The model ids are LiteLLM-namespaced so the native Gemini endpoint is used
    # (no custom endpoint key when None).
    assert cognee.config.llm["llm_model"].startswith("gemini/")
    assert "llm_endpoint" not in cognee.config.llm  # None => native resolution
    # Embeddings ALSO Gemini, SAME key (one key, no extra creds).
    assert cognee.config.embedding["embedding_provider"] == "gemini"
    assert cognee.config.embedding["embedding_api_key"] == SECRET
    assert cognee.config.embedding["embedding_model"].startswith("gemini/")
    assert "embedding_endpoint" not in cognee.config.embedding


def test_configure_does_not_leak_key_in_return_value(fake_cognee):
    """The returned module is the cognee module; describe-style state never holds it.

    The key only lives inside cognee's own config (where we handed it on purpose);
    the store never stashes it on an Amber object or returns it.
    """
    cognee = store.configure_cognee(gemini_key=SECRET)
    # The store module itself must not have captured the secret anywhere public.
    assert SECRET not in repr({k: v for k, v in vars(store).items() if not k.startswith("_")})
    # GraphAnswer (what query returns to callers) never carries a key.
    ans = store.GraphAnswer(question="q", search_type="TEMPORAL", results=["r"])
    assert SECRET not in repr(ans)
    assert cognee is fake_cognee


def test_observation_to_document_contains_real_facts_no_fabrication():
    obs = observation_from_packet(LIVE_PACKET)
    doc = store.observation_to_document(obs)
    # Real deterministic figures appear; nothing invented.
    assert "10.75" in doc
    assert "00195949689673" in doc
    assert "DE" in doc and "BE" in doc
    assert obs.observed_at in doc
    # No fabricated multi-week history language.
    assert "26 week" not in doc.lower()
    assert "month" not in doc.lower()


def test_ingest_adds_each_observation_and_runs_temporal_cognify(fake_cognee):
    obs = [observation_from_packet(LIVE_PACKET)]
    n = store.ingest(obs, gemini_key=SECRET, reset=True)
    assert n == 1
    kinds = [c[0] for c in fake_cognee._calls]
    # reset -> prune first, then one add per observation, then a temporal cognify.
    assert kinds == ["prune_data", "prune_system", "add", "cognify"]
    add_call = next(c for c in fake_cognee._calls if c[0] == "add")
    assert add_call[2] == store.DATASET_NAME
    assert add_call[3] == tuple(store.NODE_SET)
    cognify_call = next(c for c in fake_cognee._calls if c[0] == "cognify")
    assert cognify_call[1] == (store.DATASET_NAME,)
    assert cognify_call[2] is True  # temporal_cognify ON


def test_ingest_append_skips_prune(fake_cognee):
    obs = [observation_from_packet(LIVE_PACKET)]
    store.ingest(obs, gemini_key=SECRET, reset=False)
    kinds = [c[0] for c in fake_cognee._calls]
    assert "prune_data" not in kinds
    assert kinds == ["add", "cognify"]


def test_ingest_count_equals_observations_given_no_fabrication(fake_cognee):
    """Ingest exactly the observations handed to it — never invents extra captures."""
    obs = [observation_from_packet(LIVE_PACKET)]  # exactly one real packet
    n = store.ingest(obs, gemini_key=SECRET)
    assert n == 1
    n_add = sum(1 for c in fake_cognee._calls if c[0] == "add")
    assert n_add == 1  # one add for one observation, not more


def test_ingest_empty_raises(fake_cognee):
    with pytest.raises(ValueError):
        store.ingest([], gemini_key=SECRET)


def test_query_routes_to_temporal_search_type(fake_cognee):
    ans = store.query("is the gap persistent?", gemini_key=SECRET, search_type="TEMPORAL")
    assert ans.search_type == "TEMPORAL"
    search_call = next(c for c in fake_cognee._calls if c[0] == "search")
    assert search_call[2] == "TEMPORAL"
    assert "answer to:" in ans.as_text()


def test_query_default_is_graph_completion(fake_cognee):
    store.query("which countries recur?", gemini_key=SECRET)
    search_call = next(c for c in fake_cognee._calls if c[0] == "search")
    assert search_call[2] == "GRAPH_COMPLETION"


def test_ingest_does_not_write_into_signed_packet(fake_cognee, tmp_path):
    """The boundary: ingesting a packet never adds/removes files in the packet dir."""
    pkt = tmp_path / "live_packet"
    shutil.copytree(LIVE_PACKET, pkt)
    before = sorted(p.name for p in pkt.iterdir())
    captures_before = sorted(p.name for p in (pkt / "captures").iterdir())

    obs = [observation_from_packet(pkt)]
    store.ingest(obs, gemini_key=SECRET)

    after = sorted(p.name for p in pkt.iterdir())
    captures_after = sorted(p.name for p in (pkt / "captures").iterdir())
    assert after == before  # no advisory/graph file leaked into the packet
    assert captures_after == captures_before
    # No memory artifact filename appeared inside the packet.
    assert not any("legal_advisory" in n or "memory" in n or "graph" in n for n in after)
