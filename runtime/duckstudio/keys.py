"""API keys for AI vendors, entered in the Studio (ADR-0009).

A key is stored so it can be used, never so it can be read back: the runtime hands the Studio
only whether one is there and its last four characters, and no key goes into an event, a log
line or an error message.

Where: one JSON file outside the repository, readable by the user alone —
`$DUCKSTUDIO_KEYS`, else `$XDG_CONFIG_HOME/duckstudio/keys.json`, else
`~/.config/duckstudio/keys.json`. Outside the repo on purpose: a key in the working tree is one
`git add -A` away from a public commit.

Self-hosting: an environment variable (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
`OPENAI_API_KEY`) works too, but only for the vendors listed in `DUCKSTUDIO_VLM` — a key lying
around in the environment is not consent to send camera frames anywhere (ADR-0004). A key
typed into the Studio is that consent.

A hosted Duck Studio keeps one `KeyStore` per person; nothing here assumes there is only one.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

Source = Literal["studio", "environment"]


def default_path() -> Path:
    explicit = os.environ.get("DUCKSTUDIO_KEYS")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "duckstudio" / "keys.json"


def mask(key: str) -> str:
    """What the Studio may see of a key: that it exists, and enough to tell two apart."""
    return f"…{key[-4:]}" if len(key) >= 12 else "…"


@dataclass(frozen=True)
class KeyInfo:
    vendor: str
    source: Source
    hint: str  # mask(), never the key


class KeyStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        env: Mapping[str, str] | None = None,
        env_names: Mapping[str, str] | None = None,
    ) -> None:
        self.path = path or default_path()
        self._env = os.environ if env is None else env
        # vendor → environment variable, e.g. {"anthropic": "ANTHROPIC_API_KEY"}
        self._env_names = dict(env_names or {})
        self._lock = threading.Lock()

    # -- reading ---------------------------------------------------------------------------

    def get(self, vendor: str) -> str | None:
        """The key to call `vendor` with: the Studio's first, then an allowed environment one."""
        stored = self._read().get(vendor)
        if stored:
            return stored
        return self._from_env(vendor)

    def info(self, vendor: str) -> KeyInfo | None:
        stored = self._read().get(vendor)
        if stored:
            return KeyInfo(vendor, "studio", mask(stored))
        env_key = self._from_env(vendor)
        if env_key:
            return KeyInfo(vendor, "environment", mask(env_key))
        return None

    def _from_env(self, vendor: str) -> str | None:
        name = self._env_names.get(vendor)
        if not name or vendor not in allowed_from_env(self._env):
            return None
        return self._env.get(name) or None

    def _read(self) -> dict[str, str]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as e:
            log.warning("cannot read the key file %s: %s", self.path, type(e).__name__)
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("the key file %s is not JSON; ignoring it", self.path)
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}

    # -- writing ---------------------------------------------------------------------------

    def set(self, vendor: str, key: str) -> KeyInfo:
        key = key.strip()
        if not key:
            raise ValueError("empty key")
        with self._lock:
            data = self._read()
            data[vendor] = key
            self._write(data)
        return KeyInfo(vendor, "studio", mask(key))

    def remove(self, vendor: str) -> None:
        with self._lock:
            data = self._read()
            if data.pop(vendor, None) is not None:
                self._write(data)

    def _write(self, data: dict[str, str]) -> None:
        if not self.path.parent.exists():  # ours: only the user may look inside
            self.path.parent.mkdir(parents=True, mode=stat.S_IRWXU)
        tmp = self.path.with_name(self.path.name + ".tmp")
        # Created 0600 from the first byte, then moved over the old file: never readable by
        # others, never half written.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, self.path)


def allowed_from_env(env: Mapping[str, str]) -> set[str]:
    """Vendors whose environment key may be used: those named in `DUCKSTUDIO_VLM` (a,b,c)."""
    names = {n.strip().lower() for n in env.get("DUCKSTUDIO_VLM", "").split(",") if n.strip()}
    return {"anthropic" if n == "claude" else n for n in names}


class AiSettings:
    """Which model each vendor answers with. Not secret; kept next to the keys."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path().with_name("ai.json")
        self._lock = threading.Lock()

    def models(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, dict):
            return {}
        return {str(k): str(v) for k, v in models.items() if isinstance(v, str) and v}

    def set_model(self, vendor: str, model: str) -> None:
        with self._lock:
            models = self.models()
            models[vendor] = model
            if not self.path.parent.exists():
                self.path.parent.mkdir(parents=True, mode=stat.S_IRWXU)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps({"models": models}, indent=2, sort_keys=True) + "\n")
            os.replace(tmp, self.path)
