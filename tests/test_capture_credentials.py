"""Credential loading tests — env + gitignored .env, secrets never leaked."""

from __future__ import annotations

from amber.capture import credentials


def test_no_creds_returns_none(monkeypatch, tmp_path):
    for names in credentials._ALIASES.values():
        for n in names:
            monkeypatch.delenv(n, raising=False)
    # Point at a non-existent env file.
    assert credentials.load(env_file_path=tmp_path / "nope.env") is None


def test_proxy_mode_from_env(monkeypatch, tmp_path):
    for names in credentials._ALIASES.values():
        for n in names:
            monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("BRIGHTDATA_CUSTOMER_ID", "hl_test")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "resi")
    monkeypatch.setenv("BRIGHTDATA_ZONE_PASSWORD", "secret-pw")
    creds = credentials.load(env_file_path=tmp_path / "nope.env")
    assert creds is not None
    assert creds.mode == "proxy"
    assert creds.customer_id == "hl_test"


def test_api_mode_from_env(monkeypatch, tmp_path):
    for names in credentials._ALIASES.values():
        for n in names:
            monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("BRIGHTDATA_API_TOKEN", "tok123")
    creds = credentials.load(env_file_path=tmp_path / "nope.env")
    assert creds is not None
    assert creds.mode == "api"
    assert creds.api_token == "tok123"


def test_env_file_parsed(monkeypatch, tmp_path):
    for names in credentials._ALIASES.values():
        for n in names:
            monkeypatch.delenv(n, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        'BRIGHTDATA_CUSTOMER_ID="hl_file"\n'
        "BRIGHTDATA_ZONE=resi\n"
        "BRIGHTDATA_ZONE_PASSWORD='pw-from-file'\n",
        encoding="utf-8",
    )
    creds = credentials.load(env_file_path=env)
    assert creds.mode == "proxy"
    assert creds.customer_id == "hl_file"
    assert creds.password == "pw-from-file"  # quotes stripped


def test_env_overrides_file(monkeypatch, tmp_path):
    for names in credentials._ALIASES.values():
        for n in names:
            monkeypatch.delenv(n, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "BRIGHTDATA_CUSTOMER_ID=from_file\nBRIGHTDATA_ZONE=z\nBRIGHTDATA_ZONE_PASSWORD=p\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BRIGHTDATA_CUSTOMER_ID", "from_env")
    creds = credentials.load(env_file_path=env)
    assert creds.customer_id == "from_env"  # process env wins


def test_repr_and_describe_redact_secrets():
    creds = credentials.BrightDataCredentials(
        mode="proxy", customer_id="c", zone="z", password="SUPERSECRET", api_token="TOK"
    )
    text = repr(creds)
    assert "SUPERSECRET" not in text
    assert "TOK" not in text
    assert "<set>" in text

    desc = credentials.describe(creds)
    assert "SUPERSECRET" not in str(desc)
    assert desc["has_password"] is True
    assert desc["mode"] == "proxy"


def test_describe_none():
    assert credentials.describe(None) == {"present": False, "mode": None}
