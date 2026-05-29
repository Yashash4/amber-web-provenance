"""Tests for the TriggerWare HTTP client — mocked transport, no live calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amber.workflow import client as tw


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, *, text: str | None = None):
        self.status_code = status_code
        self._payload = payload
        if text is not None:
            self.text = text
        else:
            self.text = json.dumps(payload) if payload is not None else ""
        self.content = self.text.encode("utf-8")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeSession:
    """Records requests and replays a scripted queue of responses."""

    def __init__(self, responses: list[_FakeResponse]):
        self.headers: dict[str, str] = {}
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.closed = False

    def request(self, method, url, data=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "body": json.loads(data) if data else None}
        )
        if not self._responses:
            raise AssertionError(f"no scripted response for {method} {url}")
        return self._responses.pop(0)

    def close(self):
        self.closed = True


def _client_with(
    monkeypatch, responses: list[_FakeResponse]
) -> tuple[tw.TriggerWareClient, _FakeSession]:
    sess = _FakeSession(responses)

    class _FakeRequests:
        @staticmethod
        def Session():  # noqa: N802 (mimic requests API)
            return sess

    monkeypatch.setitem(__import__("sys").modules, "requests", _FakeRequests)
    client = tw.TriggerWareClient(api_key="TEST_KEY_NOT_REAL")
    return client, sess


# -- key loading --------------------------------------------------------- #
def test_load_api_key_from_env(monkeypatch):
    monkeypatch.setenv("TRIGGERWARE_API_KEY", "  envkey123  ")
    assert tw.load_api_key() == "envkey123"


def test_load_api_key_from_env_file_with_spaces(tmp_path: Path, monkeypatch):
    for name in tw._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("TRIGGERWARE_API_KEY = filekey456\n", encoding="utf-8")
    assert tw.load_api_key(env) == "filekey456"


def test_load_api_key_missing_raises(tmp_path: Path, monkeypatch):
    for name in tw._KEY_ALIASES:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(tw.APIKeyMissing):
        tw.load_api_key(tmp_path / "nope.env")


def test_describe_key_state_never_returns_the_value(monkeypatch):
    monkeypatch.setenv("TRIGGERWARE_API_KEY", "supersecret")
    state = tw.describe_key_state()
    assert state["present"] is True
    assert "supersecret" not in json.dumps(state)


def test_client_sets_api_key_header_not_logged(monkeypatch):
    client, sess = _client_with(monkeypatch, [_FakeResponse(200, [])])
    assert sess.headers["Api-Key"] == "TEST_KEY_NOT_REAL"
    client.list_triggers()
    # The key is in the session header (private), never echoed into call records.
    assert "TEST_KEY_NOT_REAL" not in json.dumps(sess.calls)


# -- API surface --------------------------------------------------------- #
def test_query_parses_signature_and_rows(monkeypatch):
    payload = {"sql": "SELECT 4", "signature": ["result"], "rows": [[4]], "error": None}
    client, sess = _client_with(monkeypatch, [_FakeResponse(200, payload)])
    result = client.query("what is 2 plus 2")
    assert result.rows == [[4]]
    assert result.as_records() == [{"result": 4}]
    assert sess.calls[0]["method"] == "POST"
    assert sess.calls[0]["url"].endswith("/query")


def test_query_with_language_sql(monkeypatch):
    payload = {"sql": "SELECT 1", "signature": ["x"], "rows": [[1]]}
    client, sess = _client_with(monkeypatch, [_FakeResponse(200, payload)])
    client.query("SELECT 1", language="sql")
    assert sess.calls[0]["body"] == {"query": "SELECT 1", "language": "sql"}


def test_create_trigger_posts_name_query_schedule(monkeypatch):
    payload = {
        "name": "amber_x",
        "query": "SELECT 1",
        "schedule": 300,
        "status": "enabled",
        "delivery": None,
        "created_at": "2026-05-29T00:00:00Z",
    }
    client, sess = _client_with(monkeypatch, [_FakeResponse(200, payload)])
    trig = client.create_trigger("amber_x", "SELECT 1", schedule=300)
    assert trig.name == "amber_x"
    assert trig.schedule == 300
    assert sess.calls[0]["body"] == {"name": "amber_x", "query": "SELECT 1", "schedule": 300}


def test_poll_parses_added_deleted(monkeypatch):
    client, _ = _client_with(
        monkeypatch, [_FakeResponse(200, {"added": [[1, "DE"]], "deleted": []})]
    )
    delta = client.poll_trigger("amber_x")
    assert delta.added == [[1, "DE"]]
    assert delta.deleted == []
    assert delta.fired is True


def test_poll_empty_delta_not_fired(monkeypatch):
    client, _ = _client_with(monkeypatch, [_FakeResponse(200, {"added": [], "deleted": []})])
    assert client.poll_trigger("amber_x").fired is False


def test_list_triggers(monkeypatch):
    client, _ = _client_with(
        monkeypatch,
        [_FakeResponse(200, [{"name": "t1", "query": "q", "schedule": 60, "status": "enabled"}])],
    )
    triggers = client.list_triggers()
    assert len(triggers) == 1
    assert triggers[0].name == "t1"


def test_delete_trigger_204_no_body(monkeypatch):
    client, sess = _client_with(monkeypatch, [_FakeResponse(204)])
    client.delete_trigger("amber_x")
    assert sess.calls[0]["method"] == "DELETE"


def test_update_trigger_requires_a_field(monkeypatch):
    client, _ = _client_with(monkeypatch, [])
    with pytest.raises(ValueError):
        client.update_trigger("amber_x")


def test_non_2xx_raises_with_detail(monkeypatch):
    client, _ = _client_with(
        monkeypatch, [_FakeResponse(500, {"detail": "SqlProblem: parse error"})]
    )
    with pytest.raises(tw.TriggerWareError) as ei:
        client.query("garbage that is not sql", language="sql")
    assert ei.value.status == 500
    assert "SqlProblem" in json.dumps(ei.value.detail)


def test_error_is_surfaced_not_swallowed(monkeypatch):
    """A failed call must raise, never return an empty/fake success."""
    client, _ = _client_with(monkeypatch, [_FakeResponse(403, text="Forbidden")])
    with pytest.raises(tw.TriggerWareError):
        client.list_triggers()
