"""Cognee configuration for the agent-memory layer — Gemini LLM backend.

Cognee (the self-hosted knowledge/temporal graph engine) needs an LLM provider
and an embedding model. We point both at Google **Gemini** using the direct
``GEMINI_API_KEY`` (read from the process env or the gitignored ``code/.env``;
the .env line is written ``GEMINI_API_KEY = <value>`` with spaces around ``=``,
so both key and value are stripped). **The key is never printed, logged, or
placed in any returned object.**

Cognee routes LLM/embedding calls through LiteLLM. We select the native Gemini
provider (``llm_provider="gemini"``) and pass LiteLLM-namespaced model ids
(``gemini/<model>``) so LiteLLM resolves Google's Generative Language endpoint
itself — no custom endpoint override, and the single ``GEMINI_API_KEY`` covers
both chat and embeddings, so the memory layer needs **no extra keys**.

This is a Phase-2 module; it does not import or touch the Phase-1 signed-packet
core. ``cognee`` itself is imported lazily by :mod:`amber.memory.store` so this
config module (and the unit suite) import cleanly without the package present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The gitignored env file (code/.env), resolved relative to this file:
# amber/memory/config.py -> code/.env
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

# Accepted env names for the direct Gemini key (first non-empty wins).
_KEY_ALIASES: tuple[str, ...] = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY")

# LiteLLM resolves Google's Generative Language endpoint from the ``gemini/``
# model namespace itself, so no custom endpoint is needed (and overriding it with
# an OpenAI-compatible URL makes the connection test hang). ``None`` => LiteLLM's
# native Gemini resolution, which the single GEMINI_API_KEY authenticates for both
# chat and embeddings (no extra keys, free-tier friendly).
GEMINI_LLM_ENDPOINT = None

# Free-tier-friendly defaults, as LiteLLM model ids (the ``gemini/`` prefix routes
# to Google's native API). gemini-2.5-flash is fast + cheap and has its own
# per-model free-tier daily quota; gemini-embedding-001 is Gemini's current
# embedding model (3072 dims), both confirmed responsive on the key.
DEFAULT_LLM_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_EMBEDDING_MODEL = "gemini/gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS = 3072
# gemini-embedding-001 accepts up to 2048 input tokens; we ingest tiny strings so
# this is comfortable headroom and keeps each call inside the free tier.
DEFAULT_EMBEDDING_MAX_TOKENS = 2048


class GeminiKeyMissing(RuntimeError):
    """No Gemini API key found in the process env or code/.env."""


@dataclass(frozen=True)
class MemoryConfig:
    """The resolved, secret-free configuration for the Cognee backend.

    Holds the model ids + endpoint, but NEVER the API key itself — the key is
    resolved separately by :func:`load_gemini_key` and handed straight to Cognee.
    """

    llm_provider: str = "gemini"
    llm_model: str = DEFAULT_LLM_MODEL
    llm_endpoint: str | None = GEMINI_LLM_ENDPOINT
    embedding_provider: str = "gemini"
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_endpoint: str | None = GEMINI_LLM_ENDPOINT
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS
    embedding_max_tokens: int = DEFAULT_EMBEDDING_MAX_TOKENS


DEFAULT_CONFIG = MemoryConfig()


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a ``KEY = VALUE`` .env file, stripping spaces around ``=``.

    Handles the Gemini key line shape ``GEMINI_API_KEY = AIza...`` (spaces around
    the equals) by stripping both sides. Strips matching surrounding quotes from
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


def load_gemini_key(env_file_path: Path | None = None) -> str:
    """Resolve the Gemini key from the process env, then code/.env.

    Process env wins over the file. Raises :class:`GeminiKeyMissing` if no usable
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

    raise GeminiKeyMissing(
        "no Gemini API key found: set GEMINI_API_KEY in the environment or in "
        f"{ENV_FILE} (the line may be 'GEMINI_API_KEY = <key>')."
    )


def describe_key_state(env_file_path: Path | None = None) -> dict:
    """A SECRET-FREE description of whether a Gemini key is resolvable (for logs).

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
