# Duck Studio

A visual studio for building behaviors for the [Microduck](https://github.com/pollen-robotics/microduck)
without writing code: trigger → perception → skills → stop conditions, clicked together as a
vertical step list, tested in simulation, sent to the duck, shared on the Hugging Face Hub.
Underneath sits a small, documented Python runtime that developers can clone, extend and
keep building with Claude Code.

> Not affiliated with Pollen Robotics or Hugging Face. Apache-2.0, like upstream.
> The UI is German first (`de`), English follows. Code, docs and commits are English.

## Status: M0 — scaffold (2026-09-19)

| Piece | State |
| --- | --- |
| Skill manifest + behavior pack schemas (pydantic, zod, JSON Schema golden files) | done |
| `mock` backend, contract tests, safety gate (clamp · battery · preconditions · rate limit · e-stop bypass) | done |
| Runtime API (`/api/health`, `/api/skills`, `/api/behaviors`, `/api/frame`, `/api/stop`, `/ws/events`) | done |
| Studio shell: skills panel, step list of `follow-me`, live panel with camera + Notstopp + log | done, read-only |
| Upstream API verified against `microduck@344925c` (0.14.1) → `docs/upstream-notes.md` | done |
| `sim` backend against duck-sim (M1), executor + follow-me (M2), editing in the Studio (M3), real duck (M4) | next |

Roadmap and rules live in [`CLAUDE.md`](CLAUDE.md); decisions in [`docs/adr/`](docs/adr/).

## Quickstart (simulation is the normal state; today the mock stands in)

```bash
# runtime
cd runtime && uv sync && uv run pytest -q
DUCKSTUDIO_BACKEND=mock uv run python -m duckstudio        # http://127.0.0.1:8000/api/health
```

```bash
# studio (second terminal)
cd studio && pnpm install && pnpm dev                        # http://localhost:5173
```

The Studio talks only to the runtime; the runtime talks to one backend
(`DUCKSTUDIO_BACKEND=mock|sim|duck`). With `mock` you get a deterministic duck that walks
when told to, a fake person in the ToF grid and a camera frame.

## Layout

```
CLAUDE.md          handover, decisions, working rules (German)
docs/adr/          architecture decision records
docs/concepts/     skill manifest, behavior pack, backend interface
docs/schemas/      JSON Schemas (golden files, exported from pydantic)
docs/upstream-notes.md  what we verified about the Microduck API, with commit hashes
runtime/           Python 3.12 · uv · FastAPI · pydantic v2 — executor, backends, API
studio/            React · TypeScript · Vite · Zustand · zod — the visual editor
skills/            *.skill.yaml — building blocks (walk, look_around, quack, getup, ...)
behaviors/         *.behavior.yaml — behavior packs, follow-me first
sim/               wrapper around upstream duck-sim (pinned checkout, never vendored)
```

## Safety, in one paragraph

Only intents and named behaviors ever reach a duck, never joint commands. Every movement
intent passes the `IntentGate`: clamped to the manifest's bounds (upstream clamps nothing),
refused under 15 % battery or when a precondition fails, rate-limited. `stop()` bypasses all
of it. The deadman lives in `robotd` (500 ms); our executor's heartbeat is simply resending
`robot.move`. Camera frames leave the runtime only to your Studio unless a behavior opts into
a VLM, which the Studio then shows in red. Tests for each of these are in
`runtime/tests/safety/`.

## Upstream

- [pollen-robotics/microduck](https://github.com/pollen-robotics/microduck) — daemons, `duck-ipc-proto`, `scripts/duck-sim`
- [pollen-robotics/microduck_rl](https://github.com/pollen-robotics/microduck_rl) — MuJoCo + PPO, policies
- [joeynyc/awesome-microduck](https://github.com/joeynyc/awesome-microduck), [joeynyc/microduck-mcp](https://github.com/joeynyc/microduck-mcp) — community
