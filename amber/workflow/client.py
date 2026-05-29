"""TriggerWare.ai API client — the real queryable-triggers-from-data platform.

What TriggerWare.ai is (confirmed live against the key on 2026-05-29, and from
https://docs.triggerware.com/): a "SQL Over Everything" platform that exposes
external data sources as queryable virtual tables (connectors) and lets you
register **triggers** — a saved SQL query + a poll schedule. TriggerWare runs
the query on the schedule and accumulates the *deltas* (rows ADDED / DELETED
since the last poll); your agent polls those deltas and acts on them. This is
the event-driven primitive Amber plugs into.

Base URL:  ``https://api.triggerware.com``
Auth:      ``Api-Key: <key>`` request header.

API surface used by Amber (all verified live with the project key):

  * ``POST /query``                  NL or SQL -> {sql, signature, rows, error}
  * ``GET  /triggers``               list triggers
  * ``POST /triggers``               create {name, query(SQL), schedule, delivery?}
  * ``POST /triggers/{name}/poll``   -> {added: [[...]], deleted: [[...]]}
  * ``PATCH  /triggers/{name}``      update query/schedule/status
  * ``DELETE /triggers/{name}``      delete (HTTP 204)
  * ``PUT  /connectors/installed/{name}``  install a connector

The API key is read from ``TRIGGERWARE_API_KEY`` in the process env or the
gitignored ``code/.env`` (the .env line may be written ``TRIGGERWARE_API_KEY =
<value>`` with spaces around ``=`` — both sides are stripped). **The key is
never printed, logged, or placed in any returned object.** This is a Phase-2
module; it does not touch the Phase-1 signed-packet core.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TRIGGERWARE_BASE_URL = "https://api.triggerware.com"

# The gitignored env file (code/.env), resolved relative to this file:
# amber/workflow/client.py -> code/.env
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

# Accepted env names for the TriggerWare key (first non-empty wins).
_KEY_ALIASES: tuple[str, ...] = (
    "TRIGGERWARE_API_KEY",
    "TRIGGERWARE_KEY",
    "TRIGGERWARE_API_TOKEN",
    "TW_API_KEY",
)

# Network timeout (seconds) for every TriggerWare call.
_TIMEOUT_S = 60.0


class APIKeyMissing(RuntimeError):
    """No TriggerWare API key found in the process env or code/.env."""


class TriggerWareError(RuntimeError):
    """A TriggerWare API call failed. Carries status + a redacted-safe message."""

    def __init__(self, message: str, *, status: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a ``KEY = VALUE`` .env file, stripping spaces around ``=``.

    Strips matching surrounding quotes from values. Missing file -> empty dict.
    Never exports to the process env (we resolve explicitly).
    """
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def load_api_key(env_file_path: Path | None = None) -> str:
    """Resolve the TriggerWare API key from the process env, then code/.env.

    Process env wins over the file. Raises :class:`APIKeyMissing` if no usable
    key is found. The returned value is the secret — callers must never print it.
    """
    for name in _KEY_ALIASES:
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip()
    env_file = _parse_env_file(env_file_path or ENV_FILE)
    for name in _KEY_ALIASES:
        v = env_file.get(name)
        if v and v.strip():
            return v.strip()
    raise APIKeyMissing(
        "no TriggerWare API key found: set TRIGGERWARE_API_KEY in the "
        f"environment or in {ENV_FILE} (the line may be "
        "'TRIGGERWARE_API_KEY = <key>')."
    )


def describe_key_state(env_file_path: Path | None = None) -> dict:
    """A SECRET-FREE description of whether a key is resolvable (for logs)."""
    for name in _KEY_ALIASES:
        v = os.environ.get(name)
        if v and v.strip():
            return {"present": True, "source": f"env:{name}"}
    env_file = _parse_env_file(env_file_path or ENV_FILE)
    for name in _KEY_ALIASES:
        v = env_file.get(name)
        if v and v.strip():
            return {"present": True, "source": f"file:{name}"}
    return {"present": False, "source": None}


@dataclass
class QueryResult:
    """The shape returned by ``POST /query``: SQL + a column signature + rows."""

    sql: str
    signature: list[str]
    rows: list[list[Any]]
    error: Any = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> QueryResult:
        return cls(
            sql=str(payload.get("sql", "")),
            signature=list(payload.get("signature") or []),
            rows=[list(r) for r in (payload.get("rows") or [])],
            error=payload.get("error"),
        )

    def as_records(self) -> list[dict[str, Any]]:
        """Zip the signature over each row into name->value records."""
        return [dict(zip(self.signature, row, strict=False)) for row in self.rows]


@dataclass
class Trigger:
    """A registered TriggerWare trigger (saved SQL query + poll schedule)."""

    name: str
    query: str
    schedule: int
    status: str = "enabled"
    delivery: Any = None
    created_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Trigger:
        return cls(
            name=str(payload["name"]),
            query=str(payload.get("query", "")),
            schedule=int(payload.get("schedule", 0)),
            status=str(payload.get("status", "")),
            delivery=payload.get("delivery"),
            created_at=payload.get("created_at"),
        )


@dataclass
class TriggerDelta:
    """The deltas a trigger accumulated since the last poll (added/removed rows)."""

    added: list[list[Any]]
    deleted: list[list[Any]]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TriggerDelta:
        return cls(
            added=[list(r) for r in (payload.get("added") or [])],
            deleted=[list(r) for r in (payload.get("deleted") or [])],
        )

    @property
    def fired(self) -> bool:
        """True iff the trigger detected any change (added or deleted rows)."""
        return bool(self.added or self.deleted)


class TriggerWareClient:
    """Thin, real HTTP client over the TriggerWare API.

    Uses ``requests`` (already an Amber dependency, Apache-2.0). The session is
    NOT logged and its ``Api-Key`` header is never echoed back. A non-2xx
    response is raised as :class:`TriggerWareError` with the parsed ``detail``,
    never silently swallowed.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = TRIGGERWARE_BASE_URL,
        env_file_path: Path | None = None,
        timeout_s: float = _TIMEOUT_S,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        key = api_key if api_key is not None else load_api_key(env_file_path)
        # Build the session lazily-importing requests so the module imports even
        # where the dep is absent (tests inject a fake session).
        import requests

        self._session = requests.Session()
        self._session.headers.update(
            {"Api-Key": key, "Content-Type": "application/json"}
        )

    # -- low-level --------------------------------------------------------- #
    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, json_body: Any = None) -> Any:
        resp = self._session.request(
            method,
            self._url(path),
            data=json.dumps(json_body) if json_body is not None else None,
            timeout=self._timeout_s,
        )
        if not (200 <= resp.status_code < 300):
            detail: Any
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            raise TriggerWareError(
                f"TriggerWare {method} {path} -> HTTP {resp.status_code}",
                status=resp.status_code,
                detail=detail,
            )
        if resp.status_code == 204 or not (resp.content or b"").strip():
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise TriggerWareError(
                f"TriggerWare {method} {path}: non-JSON 2xx body",
                status=resp.status_code,
                detail=resp.text,
            ) from exc

    # -- query (SQL Over Everything) --------------------------------------- #
    def query(self, query: str, *, language: str | None = None) -> QueryResult:
        """Run a query (natural language by default, or SQL with language='sql')."""
        body: dict[str, Any] = {"query": query}
        if language:
            body["language"] = language
        payload = self._request("POST", "/query", json_body=body)
        return QueryResult.from_payload(payload or {})

    # -- triggers ---------------------------------------------------------- #
    def list_triggers(self) -> list[Trigger]:
        payload = self._request("GET", "/triggers")
        return [Trigger.from_payload(t) for t in (payload or [])]

    def create_trigger(
        self,
        name: str,
        query: str,
        *,
        schedule: int,
        delivery: Any = None,
    ) -> Trigger:
        """Register a trigger: a saved SQL query polled every ``schedule`` seconds."""
        body: dict[str, Any] = {"name": name, "query": query, "schedule": schedule}
        if delivery is not None:
            body["delivery"] = delivery
        payload = self._request("POST", "/triggers", json_body=body)
        return Trigger.from_payload(payload or {})

    def poll_trigger(self, name: str) -> TriggerDelta:
        """Poll a trigger for the rows added/removed since the last poll."""
        payload = self._request("POST", f"/triggers/{name}/poll", json_body={})
        return TriggerDelta.from_payload(payload or {})

    def update_trigger(
        self,
        name: str,
        *,
        query: str | None = None,
        schedule: int | None = None,
        status: str | None = None,
    ) -> Trigger:
        body: dict[str, Any] = {}
        if query is not None:
            body["query"] = query
        if schedule is not None:
            body["schedule"] = schedule
        if status is not None:
            body["status"] = status
        if not body:
            raise ValueError("update_trigger: nothing to update")
        payload = self._request("PATCH", f"/triggers/{name}", json_body=body)
        return Trigger.from_payload(payload or {})

    def delete_trigger(self, name: str) -> None:
        """Delete a trigger (idempotent enough for cleanup; 404 is surfaced)."""
        self._request("DELETE", f"/triggers/{name}")

    def install_connector(self, name: str) -> Any:
        """Install a TriggerWare connector (exposes a data source as a table)."""
        return self._request("PUT", f"/connectors/installed/{name}")

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> TriggerWareClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
