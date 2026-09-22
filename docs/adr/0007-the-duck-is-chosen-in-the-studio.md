# ADR-0007: The duck is chosen in the Studio, and a switch starts from nothing

- Status: accepted
- Date: 2026-09-23

## Context

`CLAUDE.md` §3.3 says the real duck is "another backend, not another mode", and §10 says a
feature without a way in the Studio is not finished. Until now the backend was an environment
variable (`DUCKSTUDIO_BACKEND=sim|mock|duck`, plus `DUCKSTUDIO_DUCK_HOST`) read once at
startup. Somebody without a terminal could not reach the practice duck — the one backend on
which a duck actually walks today, because the simulated duck steps in place
(`microduck_rl#46`) — and in December they will not be able to reach the real one.

ADR-0006 already settled how the real duck is reached (an `ssh -L` tunnel a person opens in a
terminal; the runtime never spawns ssh). What is open is who picks the backend, and what a
change of backend must guarantee while a runtime is up.

## Decision

1. **The status in the top bar is the switch.** It says what is connected; opening it offers
   Simulation, Übungsente and Echte Ente, each with one sentence about what it is and what it
   needs. For the real duck it asks for a host name and shows the exact tunnel command to
   copy (`scripts/duck-tunnel.sh <host>`). It does not run it (ADR-0006, point 2).
2. **`PUT /api/backend {kind, host}`** swaps the backend in a running runtime. In order: the
   old duck gets `stop()` (straight to the backend — a switch is not a Notstopp and the log
   does not call it one) and is closed; perception and the reconnect loop stop; the new
   backend is wired into the gate and perception; the snapshot **forgets everything the old
   duck reported** (state, health, ToF, sightings); one connection attempt is made so the
   answer can already say "no tunnel at …"; then the loops start again.
3. **Never under a running behavior.** While the executor runs, the switch answers 409 and the
   Studio greys the choices out with a sentence, the same rule as saving or deleting a running
   behavior. Nothing is aborted from a menu in the top bar.
4. **Not remembered.** A restarted runtime comes up on `DUCKSTUDIO_BACKEND` (default `sim`),
   never on the last choice. A runtime that restarts on its own must not silently start
   talking to hardware.
5. **The host is checked as if it were going into a shell**, because it is: it appears only
   in a command a person copies into a terminal. Letters, digits, `.`, `-`, `_`, starting with
   a letter or digit — `duck.local; rm -rf ~` or `-oProxyCommand=…` are refused with 422.

## Alternatives considered

- **Environment variable only, restart to switch.** Rejected: fails §10, and "restart the
  runtime" is exactly the terminal step the Studio exists to spare people.
- **A proxy backend that forwards to whichever one is current.** It would avoid rewiring the
  gate and perception, but hide the switch inside a wrapper every call passes through; there
  are exactly two holders of the backend, so they are rewired explicitly.
- **Abort the running behavior and switch.** Safe, but surprising: a click in the top bar
  would end somebody's run. Refusing with a sentence costs one extra click.
- **Remember the choice across restarts.** Convenient for the maintainer in December, but a
  crash-and-restart that lands on the real duck is the wrong default; `DUCKSTUDIO_BACKEND=duck`
  remains for whoever wants it.
- **Let the runtime open the tunnel when "Echte Ente" is picked.** Rejected in ADR-0006 and
  still rejected: a web page should never be able to start ssh on someone's laptop.

## Consequences

- The practice duck is one click away, which makes it the obvious place to try a behavior
  while the simulated duck cannot walk.
- The real duck's first day (docs/m4-hardware-checklist.md) is: open the tunnel in a terminal,
  pick "Echte Ente" in the Studio. The environment variable still works for the contract suite.
- `/api/health` grows `backends`, `backend_error` (why the last attempt failed, in the
  backend's words) and `duck_host`. The Studio shows its own sentence first and the backend's
  words below it.
- Anything else that holds the backend in future (a planner, a recorder) has to be rewired in
  `switch_backend` too; `tests/api/test_backend_switch.py` checks the two holders there are.
