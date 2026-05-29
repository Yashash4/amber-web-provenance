"""Tests for the AI/ML API client wiring: .env parsing + key resolution.

These never touch the network. They verify the key-stripping that the spec
calls out (the .env line is ``AIMLAPI_KEY = <value>`` with spaces around ``=``)
and that the key is never leaked into a description object.
"""

from __future__ import annotations

import pytest

from amber.jury import client as jclient


def test_env_parser_strips_spaces_around_equals(tmp_path):
    """The .env line `AIMLAPI_KEY = 7f...` must parse with both sides stripped."""
    env = tmp_path / ".env"
    env.write_text("AIMLAPI_KEY = 7f0123abcdef\n", encoding="utf-8")
    parsed = jclient._parse_env_file(env)
    assert parsed["AIMLAPI_KEY"] == "7f0123abcdef"


def test_env_parser_strips_quotes(tmp_path):
    env = tmp_path / ".env"
    env.write_text('AIMLAPI_KEY = "quoted-key-value"\n', encoding="utf-8")
    parsed = jclient._parse_env_file(env)
    assert parsed["AIMLAPI_KEY"] == "quoted-key-value"


def test_env_parser_ignores_comments_and_blanks(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n\nAIMLAPI_KEY = abc\nOTHER = ignored\n", encoding="utf-8"
    )
    parsed = jclient._parse_env_file(env)
    assert parsed["AIMLAPI_KEY"] == "abc"
    assert parsed["OTHER"] == "ignored"


def test_load_api_key_from_env_file(tmp_path, monkeypatch):
    # Ensure no process-env key shadows the file under test.
    for name in jclient._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("AIMLAPI_KEY = file-key-123\n", encoding="utf-8")
    assert jclient.load_api_key(env) == "file-key-123"


def test_load_api_key_process_env_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("AIMLAPI_KEY = file-key\n", encoding="utf-8")
    monkeypatch.setenv("AIMLAPI_KEY", "process-key")
    assert jclient.load_api_key(env) == "process-key"


def test_load_api_key_missing_raises(tmp_path, monkeypatch):
    for name in jclient._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    missing = tmp_path / "does-not-exist.env"
    with pytest.raises(jclient.APIKeyMissing):
        jclient.load_api_key(missing)


def test_describe_key_state_never_leaks_value(tmp_path, monkeypatch):
    for name in jclient._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("AIMLAPI_KEY = super-secret-value\n", encoding="utf-8")
    desc = jclient.describe_key_state(env)
    assert desc["present"] is True
    assert desc["source"] == "file:AIMLAPI_KEY"
    # The secret value must not appear anywhere in the description.
    assert "super-secret-value" not in repr(desc)


def test_describe_key_state_absent(tmp_path, monkeypatch):
    for name in jclient._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    desc = jclient.describe_key_state(tmp_path / "nope.env")
    assert desc == {"present": False, "source": None}


def test_default_models_are_three_distinct_families():
    m = jclient.DEFAULT_MODELS
    ids = m.as_tuple()
    assert len(ids) == 3
    assert len(set(ids)) == 3  # three distinct model ids
    assert m.openai == "gpt-4o-mini"
    assert m.google == "google/gemini-2.0-flash"
    assert m.anthropic.startswith("claude-")
