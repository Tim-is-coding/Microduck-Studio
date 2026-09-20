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

Environment:

| Variable | Default | What it does |
| --- | --- | --- |
| `DUCKSTUDIO_BACKEND` | `sim` | which duck: `mock`, `sim`, `duck` |
| `DUCKSTUDIO_ROOT` | the repo | where `skills/` and `behaviors/` live |
| `DUCKSTUDIO_DUCK_TUNNEL` | `~/.cache/duckstudio/tunnel` | where `scripts/duck-tunnel.sh` put the local ends of the ssh forwards (ADR-0006) |
| `DUCKSTUDIO_DUCK_HOST` | – | the duck's host name, so a missing tunnel can name it |
| `DUCKSTUDIO_DUCK_CONSOLE` | `http://127.0.0.1:8080` | mediad's console through the tunnel; empty for a duck without a camera |
| `DUCKSTUDIO_VLM` | `stub` | `anthropic` sends frames to Claude for behaviors that opted in (ADR-0004); the default answers locally and sends nothing |
| `DUCKSTUDIO_VLM_MODEL` | `claude-opus-5` | model for the Claude provider (`uv sync --extra vlm`, `ANTHROPIC_API_KEY`) |
| `DUCKSTUDIO_VLM_HZ` | `0.5` | how often a standing question is asked, clamped to 2 Hz (§4) |

Layout follows `CLAUDE.md` §5. Upstream JSON-RPC method names live in one place,
`duckstudio/upstream.py`, each flagged `verified` only once `docs/upstream-notes.md` lists it
with a commit hash.
