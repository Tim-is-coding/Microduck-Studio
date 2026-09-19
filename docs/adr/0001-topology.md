# ADR-0001: Studio ↔ Runtime ↔ Backend topology

- Status: accepted
- Date: 2026-09-19

## Context

Duck Studio lets non-technical users compose behaviors for the Microduck and run them in
simulation or on the robot. Upstream (`pollen-robotics/microduck`) exposes seven daemons
over JSON-RPC/NDJSON on Unix sockets, with `mediad` as the remote gateway and a WebSocket
path intended for LLM/server agents. Upstream's `architecture.md` leaves two things open
that we depend on: authority arbitration (gamepad vs. app vs. remote vs. autonomy) and
where a behavior/"brain" layer should live. `robotd` enforces a deadman: no commands, no
motion. The maintainer's duck arrives around December 2026; until then only `duck-sim`
exists as a target.

## Decision

Three tiers, one direction of trust:

```
Browser: Studio ──HTTP/WS──► Runtime (Python) ──JSON-RPC/NDJSON──► duck-sim (Unix sockets)
                              Executor · Perception ·              duck (ssh tunnel or WebRTC
                              Skill registry · (Planner, phase 2)  datachannel, M4 ADR)
                              Backend protocol: mock | sim | duck
```

Transport note (verified 2026-09-19, `docs/upstream-notes.md`): upstream has no inbound
WebSocket for agents yet; the simulation exposes plain Unix sockets, the real duck is
reached through `ssh -L` tunnels or mediad's WebRTC control datachannel.

1. The Studio talks **only** to the runtime, never to the duck or to `mediad` directly.
2. The runtime owns everything safety-relevant: the deadman heartbeat, the authority
   order **e-stop > physical controller (gamepad) > executor > planner**, clamping,
   battery gating, rate limiting and the emergency stop (`CLAUDE.md` §7).
3. Backends implement one protocol (`runtime/duckstudio/backends/base.py`) and pass one
   contract test suite. `mock` is deterministic and always available; `sim` speaks to the
   real upstream daemons under MuJoCo; `duck` speaks to the robot. Simulation is the
   normal state, not a fallback (`CLAUDE.md` §3.3).
4. The executor is a behaviour tree ticking at 10 Hz, sending at most one intent per tick.
   Perception runs at two rates: local detectors 10–30 Hz, VLM 0.5–2 Hz, and the VLM is
   never inside the loop that can brake the duck.
5. Upstream JSON-RPC names live in exactly one module (`duckstudio/upstream.py`) and are
   flagged unverified until `docs/upstream-notes.md` records them with a commit hash.

## Alternatives considered

- **Studio talks to `mediad`'s WebSocket directly, no runtime.** Rejected: the deadman and
  the safety layer would live in a browser tab; closing the tab or a GC pause becomes a
  robot-safety event, and there is no place for perception at 10–30 Hz.
- **Brain layer as a daemon on the duck.** Rejected for v1 (`CLAUDE.md` §3.5): no hardware
  until December, the RK3566 cannot run a VLM, and the skill manifest is not stable enough
  to freeze into an on-robot update channel. Revisit when the manifest is stable.
- **Fork `robotd` and add behaviors there.** Rejected: `CLAUDE.md` §3.5 forbids forking; we
  stay a client of the upstream API and can update independently of the robot image.

## Consequences

- One extra network hop between Studio and duck. Acceptable: intents are low-rate; the
  50 Hz control loop stays inside `robotd`.
- The runtime must run on a laptop or server next to the duck; the README documents this.
- `mock` is the default backend in M0; `sim` becomes the default in M1 once it passes the
  contract tests. The real duck is one more backend, not a different mode.
- Authority arbitration is implemented on our side. If upstream later ships its own, the
  runtime keeps its order and defers to upstream's stricter decision.
