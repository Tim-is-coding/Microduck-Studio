"""`python -m duckstudio` — run the runtime API for the Studio."""

from __future__ import annotations

import os

import uvicorn

from .api import create_app


def main() -> None:
    host = os.environ.get("DUCKSTUDIO_HOST", "127.0.0.1")
    port = int(os.environ.get("DUCKSTUDIO_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
