"""Duck Studio runtime: executes behavior packs for the Microduck (see CLAUDE.md §4)."""

from __future__ import annotations

import os
from pathlib import Path

__version__ = "0.0.1"


def repo_root() -> Path:
    """Repository root (contains `skills/` and `behaviors/`).

    Override with `DUCKSTUDIO_ROOT` when the runtime is installed outside the repo.
    """
    env = os.environ.get("DUCKSTUDIO_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def skills_dir() -> Path:
    return repo_root() / "skills"


def behaviors_dir() -> Path:
    return repo_root() / "behaviors"
