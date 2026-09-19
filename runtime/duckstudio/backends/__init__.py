"""Backend factory. `mock` is deterministic; `sim` (M1) and `duck` (M4) speak upstream."""

from __future__ import annotations

import os
import time

from .base import DuckBackend

KINDS = ("mock", "sim", "duck")


def make_backend(kind: str | None = None, **options: object) -> DuckBackend:
    kind = kind or os.environ.get("DUCKSTUDIO_BACKEND", "mock")
    if kind == "mock":
        from .mock import MockBackend

        options.setdefault("clock", time.monotonic)
        return MockBackend(**options)  # type: ignore[arg-type]
    if kind == "sim":
        from .sim import SimBackend

        return SimBackend(**options)  # type: ignore[arg-type]
    if kind == "duck":
        from .duck import RealDuckBackend

        options.setdefault("url", os.environ.get("DUCKSTUDIO_DUCK_URL", ""))
        return RealDuckBackend(**options)  # type: ignore[arg-type]
    raise ValueError(f"unknown backend kind {kind!r}; expected one of {KINDS}")
