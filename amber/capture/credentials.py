"""Bright Data credential loading — secrets, never committed, never printed.

Credentials are read, in order of precedence, from:

  1. process ENVIRONMENT variables, then
  2. a gitignored ``code/.env`` file (KEY=VALUE lines).

Two credential shapes are supported, matching the two capture modes:

  * ``proxy`` mode (preferred for the within-country control): needs
    ``BRIGHTDATA_CUSTOMER_ID`` + ``BRIGHTDATA_ZONE`` + ``BRIGHTDATA_ZONE_PASSWORD``
    (the residential zone's super-proxy password). Sticky sessions give distinct
    residential IPs per country.
  * ``api`` mode: needs ``BRIGHTDATA_API_TOKEN`` (+ optional ``BRIGHTDATA_ZONE``)
    for the Web Unlocker request API.

Common aliases are accepted so whatever the operator has exported is found. This
module NEVER logs a secret value: :func:`describe` returns only which fields are
present (booleans), never the values, and ``__repr__`` is redacted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The gitignored env file Component 2 reads (in addition to the process env).
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

# Accepted env names per logical field (first non-empty wins).
_ALIASES: dict[str, tuple[str, ...]] = {
    "customer_id": (
        "BRIGHTDATA_CUSTOMER_ID",
        "BRIGHTDATA_CUSTOMER",
        "BRD_CUSTOMER_ID",
        "BD_CUSTOMER_ID",
    ),
    "zone": (
        "BRIGHTDATA_ZONE",
        "BRD_ZONE",
        "BD_ZONE",
        "BRIGHTDATA_RESIDENTIAL_ZONE",
    ),
    "password": (
        "BRIGHTDATA_ZONE_PASSWORD",
        "BRIGHTDATA_PASSWORD",
        "BRD_PASSWORD",
        "BD_PASSWORD",
        "BRIGHTDATA_PASS",
    ),
    "api_token": (
        "BRIGHTDATA_API_TOKEN",
        "BRIGHTDATA_API_KEY",
        "BRIGHTDATA_TOKEN",
        "BRD_API_TOKEN",
        "BD_API_TOKEN",
    ),
}


class CredentialsMissing(RuntimeError):
    """No usable Bright Data credentials were found in env or code/.env."""


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE .env file. Missing file -> empty dict.

    Ignores blank lines and ``#`` comments. Strips matching surrounding quotes
    from values. Does not export to the process env (we resolve explicitly).
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
        out[key] = val
    return out


def _resolve(field: str, env_file: dict[str, str]) -> str | None:
    """Resolve one logical field from process env, then the env-file dict."""
    for name in _ALIASES[field]:
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip()
    for name in _ALIASES[field]:
        v = env_file.get(name)
        if v and v.strip():
            return v.strip()
    return None


@dataclass
class BrightDataCredentials:
    """Resolved BD credentials + the capture mode they enable.

    ``mode`` is ``"proxy"`` or ``"api"``. Secret fields are present but the repr
    is redacted so a stray log/print never leaks them.
    """

    mode: str
    customer_id: str | None = None
    zone: str | None = None
    password: str | None = None
    api_token: str | None = None

    def __repr__(self) -> str:  # redact secrets
        def red(v: str | None) -> str:
            return "<set>" if v else "<unset>"

        return (
            f"BrightDataCredentials(mode={self.mode!r}, "
            f"customer_id={red(self.customer_id)}, zone={self.zone!r}, "
            f"password={red(self.password)}, api_token={red(self.api_token)})"
        )


def load(env_file_path: Path | None = None) -> BrightDataCredentials | None:
    """Load BD credentials from env + the gitignored code/.env.

    Returns a :class:`BrightDataCredentials` if a usable set is found, else
    ``None`` (the harness treats ``None`` as "live capture pending", NOT as an
    error and NEVER as license to fabricate). Proxy mode is preferred when both
    proxy creds and an API token are present, because proxy sticky sessions give
    the distinct-IP within-country control.
    """
    env_file = _parse_env_file(env_file_path or ENV_FILE)

    customer_id = _resolve("customer_id", env_file)
    zone = _resolve("zone", env_file)
    password = _resolve("password", env_file)
    api_token = _resolve("api_token", env_file)

    if customer_id and zone and password:
        return BrightDataCredentials(
            mode="proxy",
            customer_id=customer_id,
            zone=zone,
            password=password,
            api_token=api_token,
        )
    if api_token:
        return BrightDataCredentials(mode="api", zone=zone, api_token=api_token)
    return None


def describe(creds: BrightDataCredentials | None) -> dict:
    """A SECRET-FREE description of the credential state (for logs/reports).

    Reports which fields are present (booleans) and the mode — never any value.
    """
    if creds is None:
        return {"present": False, "mode": None}
    return {
        "present": True,
        "mode": creds.mode,
        "has_customer_id": bool(creds.customer_id),
        "has_zone": bool(creds.zone),
        "has_password": bool(creds.password),
        "has_api_token": bool(creds.api_token),
    }
