"""Backend factory. `sim` is the normal state (CLAUDE.md §3.3); `mock` is deterministic;
`duck` (M4) waits for hardware."""

from __future__ import annotations

import os
import time

from .base import DuckBackend

KINDS = ("mock", "sim", "duck")
DEFAULT_KIND = "sim"


def make_backend(kind: str | None = None, **options: object) -> DuckBackend:
    kind = kind or os.environ.get("DUCKSTUDIO_BACKEND", DEFAULT_KIND)
    if kind == "mock":
        from .mock import MockBackend

        options.setdefault("clock", time.monotonic)
        return MockBackend(**options)  # type: ignore[arg-type]
    if kind == "sim":
        from .sim import SimBackend

        console = os.environ.get("DUCKSTUDIO_SIM_CONSOLE")
        if console is not None:
            options.setdefault("console_url", console or None)
        return SimBackend(**options)  # type: ignore[arg-type]
    if kind == "duck":
        from .duck import RealDuckBackend

        options.setdefault("url", os.environ.get("DUCKSTUDIO_DUCK_URL", ""))
        return RealDuckBackend(**options)  # type: ignore[arg-type]
    raise ValueError(f"unknown backend kind {kind!r}; expected one of {KINDS}")
