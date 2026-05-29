"""Tests for the Cognee/Gemini config: .env parsing + key resolution + honesty.

These never touch the network. They verify the key-stripping the spec calls out
(the .env line is ``GEMINI_API_KEY = <value>`` with spaces around ``=``) and that
the key is never leaked into a description object.
"""

from __future__ import annotations

import pytest

from amber.memory import config as mcfg


def test_env_parser_strips_spaces_around_equals(tmp_path):
    """The .env line `GEMINI_API_KEY = AIza...` must parse with both sides stripped."""
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY = AIzaSyExampleKey123\n", encoding="utf-8")
    parsed = mcfg._parse_env_file(env)
    assert parsed["GEMINI_API_KEY"] == "AIzaSyExampleKey123"


def test_env_parser_strips_quotes(tmp_path):
    env = tmp_path / ".env"
    env.write_text('GEMINI_API_KEY = "quoted-key-value"\n', encoding="utf-8")
    parsed = mcfg._parse_env_file(env)
    assert parsed["GEMINI_API_KEY"] == "quoted-key-value"


def test_load_gemini_key_from_env_file(tmp_path, monkeypatch):
    for name in mcfg._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY = file-key-123\n", encoding="utf-8")
    assert mcfg.load_gemini_key(env) == "file-key-123"


def test_load_gemini_key_process_env_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY = file-key\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "process-key")
    assert mcfg.load_gemini_key(env) == "process-key"


def test_load_gemini_key_missing_raises(tmp_path, monkeypatch):
    for name in mcfg._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    missing = tmp_path / "does-not-exist.env"
    with pytest.raises(mcfg.GeminiKeyMissing):
        mcfg.load_gemini_key(missing)


def test_describe_key_state_never_leaks_value(tmp_path, monkeypatch):
    for name in mcfg._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY = super-secret-value\n", encoding="utf-8")
    desc = mcfg.describe_key_state(env)
    assert desc["present"] is True
    assert desc["source"] == "file:GEMINI_API_KEY"
    assert "super-secret-value" not in repr(desc)


def test_describe_key_state_absent(tmp_path, monkeypatch):
    for name in mcfg._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    desc = mcfg.describe_key_state(tmp_path / "nope.env")
    assert desc == {"present": False, "source": None}


def test_default_config_uses_gemini_for_llm_and_embeddings():
    cfg = mcfg.DEFAULT_CONFIG
    assert cfg.llm_provider == "gemini"
    assert cfg.embedding_provider == "gemini"
    # Native Gemini resolution: no custom endpoint (None) for either.
    assert cfg.llm_endpoint is None
    assert cfg.embedding_endpoint is None
    # LiteLLM-namespaced model ids so one Gemini key serves both.
    assert cfg.llm_model.startswith("gemini/")
    assert cfg.embedding_model.startswith("gemini/")
