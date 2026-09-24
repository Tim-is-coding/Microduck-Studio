"""API keys (ADR-0009): stored to be used, never to be read back."""

from __future__ import annotations

import stat
from pathlib import Path

from duckstudio.keys import KeyStore, mask

KEY = "sk-test-0123456789abcdef"
ENV_NAMES = {"anthropic": "ANTHROPIC_API_KEY", "google": "GEMINI_API_KEY"}


def test_a_stored_key_is_used_and_only_its_end_is_shown(tmp_path: Path) -> None:
    store = KeyStore(tmp_path / "cfg" / "keys.json", env={})
    info = store.set("anthropic", f"  {KEY}\n")
    assert store.get("anthropic") == KEY
    assert info.hint == "…cdef" and KEY not in info.hint
    assert store.info("anthropic").source == "studio"


def test_the_file_is_the_users_alone(tmp_path: Path) -> None:
    path = tmp_path / "cfg" / "keys.json"
    KeyStore(path, env={}).set("google", KEY)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_remove(tmp_path: Path) -> None:
    store = KeyStore(tmp_path / "keys.json", env={})
    store.set("google", KEY)
    store.remove("google")
    assert store.get("google") is None and store.info("google") is None


def test_an_environment_key_counts_only_when_the_vendor_is_named(tmp_path: Path) -> None:
    """A key lying around in the environment is not consent (ADR-0004)."""
    env = {"ANTHROPIC_API_KEY": KEY}
    assert KeyStore(tmp_path / "k.json", env=env, env_names=ENV_NAMES).get("anthropic") is None
    env["DUCKSTUDIO_VLM"] = "claude, google"
    store = KeyStore(tmp_path / "k.json", env=env, env_names=ENV_NAMES)
    assert store.get("anthropic") == KEY
    assert store.info("anthropic").source == "environment"


def test_a_broken_file_is_no_key_and_no_crash(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    path.write_text("{not json")
    assert KeyStore(path, env={}).get("google") is None


def test_short_keys_show_nothing() -> None:
    assert mask("abc") == "…"
