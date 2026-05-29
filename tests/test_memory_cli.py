"""Tests for the ``amber-memory`` CLI.

The ``persistence`` subcommand runs OFFLINE (no Gemini), so it is fully tested
here against the real signed packet. ``ingest``/``query`` are tested with cognee
mocked. Every path asserts the boundary: the CLI never modifies the signed
packet, and the Gemini key is never printed.
"""

from __future__ import annotations

import json
import shutil
import sys
import types
from pathlib import Path

import amber.memory.cli as mcli
from amber.memory import config as mcfg

LIVE_PACKET = Path(__file__).resolve().parent.parent / "samples" / "live_packet"
FLOOR_PACKET = Path(__file__).resolve().parent.parent / "samples" / "floor_demo_packet"
SECRET = "AIza-cli-secret-key-DO-NOT-LEAK"


def test_persistence_on_real_packet_is_baseline(capsys):
    rc = mcli.main(["persistence", str(LIVE_PACKET)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "VERDICT: BASELINE" in out
    assert "00195949689673" in out
    assert "10.75" in out
    assert "one-point baseline" in out
    # Honest framing — never a fabricated multi-week chart.
    assert "26 week" not in out.lower()


def test_persistence_json_output(capsys):
    rc = mcli.main(["persistence", str(LIVE_PACKET), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{"):])
    assert payload["persistence"][0]["verdict"] == "BASELINE"
    assert payload["recurrence"]["n_observations"] == 1


def test_persistence_multiple_packets_recurrence(capsys, tmp_path):
    """Two captures of the SAME GTIN -> recurrence + a real-window phrasing."""
    # Copy the real packet twice with different timestamps to simulate two real
    # captures (the copies are REAL captured bytes; only the dir name differs —
    # this is reusing the same real packet, not fabricating price history).
    p1 = tmp_path / "cap1"
    shutil.copytree(LIVE_PACKET, p1)
    rc = mcli.main(["persistence", str(p1)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "BASELINE" in out  # one capture each dir -> baseline, honest


def test_persistence_unreadable_packet_errors(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = mcli.main(["persistence", str(empty)])
    assert rc == 2


def test_persistence_does_not_modify_packet(tmp_path):
    pkt = tmp_path / "live_packet"
    shutil.copytree(LIVE_PACKET, pkt)
    before = sorted(p.name for p in pkt.iterdir())
    mcli.main(["persistence", str(pkt)])
    assert sorted(p.name for p in pkt.iterdir()) == before


def test_ingest_without_key_fails_clearly(monkeypatch, capsys):
    for name in mcfg._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    # Point the env-file resolver at a nonexistent file so no key is found.
    monkeypatch.setattr(mcfg, "ENV_FILE", Path("/nonexistent/.env"))
    rc = mcli.main(["ingest", str(LIVE_PACKET)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no Gemini API key" in err


def test_creds_never_prints_key(monkeypatch, capsys, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"GEMINI_API_KEY = {SECRET}\n", encoding="utf-8")
    monkeypatch.setattr(mcfg, "ENV_FILE", env)
    for name in mcfg._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    rc = mcli.main(["creds"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "present=True" in out
    assert SECRET not in out  # the key value is NEVER printed


def _inject_fake_cognee(monkeypatch):
    """Inject a minimal fake cognee so the CLI ingest/query path runs offline."""
    calls: list = []
    mod = types.ModuleType("cognee")

    class _Cfg:
        def set_llm_config(self, c):
            calls.append(("llm", c.get("llm_api_key")))

        def set_embedding_config(self, c):
            calls.append(("emb", c.get("embedding_api_key")))

    class _Prune:
        async def prune_data(self):
            calls.append(("prune_data",))

        async def prune_system(self, metadata=True):
            calls.append(("prune_system",))

    class _ST:
        GRAPH_COMPLETION = "GRAPH_COMPLETION"
        TEMPORAL = "TEMPORAL"

    async def add(data, dataset_name=None, node_set=None):
        calls.append(("add",))

    async def cognify(datasets=None, temporal_cognify=False):
        calls.append(("cognify", temporal_cognify))

    async def search(query_text, query_type=None, datasets=None, top_k=10):
        calls.append(("search", query_type))
        return ["graph says: persistent across captures"]

    mod.config = _Cfg()
    mod.prune = _Prune()
    mod.SearchType = _ST
    mod.add = add
    mod.cognify = cognify
    mod.search = search
    mod._calls = calls
    monkeypatch.setitem(sys.modules, "cognee", mod)
    return mod


def test_ingest_with_mocked_cognee(monkeypatch, capsys, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"GEMINI_API_KEY = {SECRET}\n", encoding="utf-8")
    monkeypatch.setattr(mcfg, "ENV_FILE", env)
    for name in mcfg._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    fake = _inject_fake_cognee(monkeypatch)

    rc = mcli.main(["ingest", str(LIVE_PACKET)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ingested 1 observation" in out
    assert "Real captures only" in out
    # The honest window line is shown on ingest.
    assert "one-point baseline" in out
    # The key was handed to BOTH llm + embedding config, never printed.
    assert ("llm", SECRET) in fake._calls
    assert ("emb", SECRET) in fake._calls
    assert SECRET not in out
    assert ("cognify", True) in fake._calls  # temporal cognify


def test_query_with_mocked_cognee_temporal(monkeypatch, capsys, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"GEMINI_API_KEY = {SECRET}\n", encoding="utf-8")
    monkeypatch.setattr(mcfg, "ENV_FILE", env)
    for name in mcfg._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    fake = _inject_fake_cognee(monkeypatch)

    rc = mcli.main(["query", "has this SKU shown a gap before?", "--temporal"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TEMPORAL" in out
    assert "graph says" in out
    assert ("search", "TEMPORAL") in fake._calls
    assert SECRET not in out
