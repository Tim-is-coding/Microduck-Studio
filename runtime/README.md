# duckstudio (runtime)

Python 3.12 runtime for Duck Studio. It loads skill manifests (`../skills`) and behavior
packs (`../behaviors`), talks to one backend (`mock` | `sim` | `duck`) through the
`DuckBackend` protocol, enforces the safety invariants from `CLAUDE.md` §7 and serves the
Studio over HTTP/WebSocket.

```bash
uv sync
uv run pytest -q
DUCKSTUDIO_BACKEND=mock uv run python -m duckstudio   # http://localhost:8000/api/health
```

Layout follows `CLAUDE.md` §5. Upstream JSON-RPC method names live in one place,
`duckstudio/upstream.py`, each flagged `verified` only once `docs/upstream-notes.md` lists it
with a commit hash.
