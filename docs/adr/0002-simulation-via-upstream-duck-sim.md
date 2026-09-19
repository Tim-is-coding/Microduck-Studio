# ADR-0002: Simulation runs through upstream `duck-sim`, and `sim` is the default backend

- Status: accepted
- Date: 2026-09-19

## Context

`CLAUDE.md` §8 M1 asked for "duck-sim reproducible via docker-compose". Verified upstream
(`docs/upstream-notes.md`, "duck-sim"): there is no compose file; `scripts/duck-sim` builds the
daemons with cargo, starts the MuJoCo body from `microduck_rl`'s venv (`duck-body`), then
`tofd --sim`, `configd`, `updaterd`, `robotd --sim`, optionally `mediad --sim-camera`. Its
container form (`boot`) needs `systemd-nspawn` and `sudo` on Linux. The maintainer develops
on macOS. Sockets land under `~/.cache/duck-sim/`; the body needs wall-clock realtime ≥ 1.0×
or the policies cannot balance — a constraint that makes containers on macOS (a Linux VM
underneath) a bad fit for the physics half anyway.

`CLAUDE.md` §3.3: simulation is the normal state; the Studio starts with
"Simulation (MuJoCo) · Ente nicht verbunden" and is fully usable.

## Decision

1. We do not package the simulator. `sim/fetch-upstream.sh` pins both upstream repos into
   git-ignored checkouts (`sim/upstream`, `sim/upstream-rl`) and creates the RL venv;
   `sim/up.sh` sets the environment duck-sim wants (headless, camera on duck-a, RL path) and
   `exec`s the upstream script. Everything else stays upstream's.
2. The `sim` backend (`runtime/duckstudio/backends/sim.py`) dials duck-sim's Unix sockets
   directly with JSON-RPC/NDJSON — no tunnel, no adapter. The same class (`IpcBackend`) will
   serve the real duck over `ssh -L` in M4.
3. `sim` is the runtime's default backend from M1 on. When the sockets are missing the
   runtime says so in the event log and retries every few seconds; the Studio stays usable
   for editing. `DUCKSTUDIO_BACKEND=mock` remains for tests and offline work.
4. In CI the `sim` contract runs against a protocol double (`tests/backends/fake_robotd.py`)
   that mirrors the verified wire shapes and refuses unknown params like upstream. The double
   is not a simulation; the real check is `DUCKSTUDIO_SIM=1 pytest` against duck-sim.

## Alternatives considered

- **docker-compose with duck-sim inside.** Rejected: nothing upstream to compose; MuJoCo in a
  Linux VM on macOS runs below realtime; `boot` mode needs systemd-nspawn. Revisit for a
  Linux CI runner that exercises the real daemons.
- **Our own Python re-implementation of robotd's control chain** (what microduck-mcp's
  `sim` transport does). Rejected: it is a second robotd that drifts; `CLAUDE.md` §3.3 wants
  the real daemons.
- **`mock` stays default until hardware.** Rejected: contradicts §3.3 and hides the sim
  integration from every Studio session.

## Consequences

- A developer needs Rust (`cargo`), `uv`, and for the camera on macOS `gstreamer` via
  Homebrew. `sim/README.md` lists the steps; the first `sim/up.sh` compiles for minutes.
- The fake daemon must be updated whenever upstream-notes change; the `DUCKSTUDIO_SIM=1`
  run is the guard against drift.
- `CLAUDE.md` §8 M1 wording is corrected to point here.
