"""AI/ML API client wiring for the Layer-2 jury.

Uses the OpenAI SDK pointed at the AI/ML API gateway
(``https://api.aimlapi.com/v1``), which exposes OpenAI, Google, and Anthropic
models behind one OpenAI-compatible endpoint. That single gateway is what makes
the three-model "jury" honest: three *causally different* model families (not
three temperatures of one model) classify the same signed observation.

The API key is read from ``AIMLAPI_KEY`` in the process env or the gitignored
``code/.env`` (NOTE: the .env line is written ``AIMLAPI_KEY = <value>`` with
spaces around ``=`` — both key and value are stripped). **The key is never
printed, logged, or placed in any returned object.**

This is a Phase-2 module; it does not touch the Phase-1 signed-packet core.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# AI/ML API OpenAI-compatible gateway base URL.
AIMLAPI_BASE_URL = "https://api.aimlapi.com/v1"

# The gitignored env file (code/.env), resolved relative to this file:
# amber/jury/client.py -> code/.env
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

# Accepted env names for the AI/ML API key (first non-empty wins).
_KEY_ALIASES: tuple[str, ...] = ("AIMLAPI_KEY", "AIML_API_KEY", "AI_ML_API_KEY")

# --------------------------------------------------------------------------- #
# The three jury model IDs (resolved against client.models.list() on the
# AI/ML API gateway on 2026-05-29). One model per family:
#   * OpenAI   — gpt-4o-mini (present and responsive on the gateway)
#   * Google   — google/gemini-2.0-flash (the working Gemini id)
#   * Anthropic— claude-sonnet-4-5-20250929 (the spec's claude-3-5-sonnet-
#     20240620 returns 404 on this gateway; this is the correct current
#     AI/ML-API Anthropic id and was confirmed responsive)
# These are configurable constants; override per-call via JuryModels.
# --------------------------------------------------------------------------- #
OPENAI_MODEL_ID = "gpt-4o-mini"
GOOGLE_MODEL_ID = "google/gemini-2.0-flash"
ANTHROPIC_MODEL_ID = "claude-sonnet-4-5-20250929"


@dataclass(frozen=True)
class JuryModels:
    """The three model IDs that make up the jury (one per family)."""

    openai: str = OPENAI_MODEL_ID
    google: str = GOOGLE_MODEL_ID
    anthropic: str = ANTHROPIC_MODEL_ID

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.openai, self.google, self.anthropic)


DEFAULT_MODELS = JuryModels()


class APIKeyMissing(RuntimeError):
    """No AI/ML API key found in the process env or code/.env."""


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a ``KEY = VALUE`` .env file, stripping spaces around ``=``.

    Handles the AI/ML key line shape ``AIMLAPI_KEY = 7f...`` (spaces around the
    equals) by stripping both sides. Strips matching surrounding quotes from
    values. Missing file -> empty dict. Never exports to the process env.
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
    """Resolve the AI/ML API key from the process env, then code/.env.

    Process env wins over the file. Raises :class:`APIKeyMissing` if no usable
    key is found anywhere. The returned value is the secret — callers must never
    print or log it.
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
        "no AI/ML API key found: set AIMLAPI_KEY in the environment or in "
        f"{ENV_FILE} (the line may be 'AIMLAPI_KEY = <key>')."
    )


def make_client(api_key: str | None = None, env_file_path: Path | None = None):
    """Build an OpenAI SDK client pointed at the AI/ML API gateway.

    Imports ``openai`` lazily so the module imports cleanly (and tests that mock
    the client run) even in an environment without the SDK installed. The key is
    resolved via :func:`load_api_key` when not supplied; it is passed straight
    into the SDK and never stored on any Amber object.
    """
    from openai import OpenAI  # lazy import: keeps the dep optional at import time

    key = api_key if api_key is not None else load_api_key(env_file_path)
    return OpenAI(base_url=AIMLAPI_BASE_URL, api_key=key)


def describe_key_state(env_file_path: Path | None = None) -> dict:
    """A SECRET-FREE description of whether a key is resolvable (for logs).

    Reports presence (boolean) and where it would come from — never the value.
    """
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
