# Executor

`runtime/duckstudio/executor/tree.py` runs a behavior pack as a vertical step list with side
branches (`CLAUDE.md` §3.2, §6.4). No general behaviour-tree library: the shape is fixed
(trigger → steps → always-rules) and every branch hangs off a step.

## One tick, 10 Hz

1. Refresh the step context in the shared `Snapshot` (`now`, `elapsed_s`, `budget_s`,
   `target_distance_m`). Perception writes into the same object at its own rates; the tick
   never waits for it.
2. **Gamepad preemption**: any `pad.report` frame with events → `robot.stop`, state
   `preempted`, nothing else goes out. Authority order (§4) is e-stop > gamepad > executor.
3. **`always` rules** are evaluated before the active node. When one fires
   (`on: fallen`), its actions run in order: skill ids as one-shot skill runs, then a reserved
   word — `resume` returns to the interrupted step, `abort` fails the behavior, `stop` halts.
   A rule that fires more than three times in a row fails the behavior ("Erholung klappt
   nicht"). An action refused for a precondition (getup while already standing) is skipped.
4. **The active step**:
   - `perceive: person.nearest` succeeds when a fresh detection (< 1 s) exists. `on_none`
     runs its skill for `seconds` (look_around sweeps the head), then `retry` / `abort` /
     `continue`.
   - `skill:` runs the skill with params resolved from `with` (plus manifest `ui` defaults).
     End conditions come first — `until` (speech, elapsed, signal), then the manifest's
     `terminates_on` (`fallen`/`motor_hot` fail, everything else succeeds, e.g.
     `target_reached`) — and only then at most one intent or behavior goes out through the
     `IntentGate`, no faster than the manifest's `rate_hz`.
   - `wait:` counts down.
5. Speech heard this tick is consumed; the watchdog is petted.

## Heartbeat = resending `robot.move`

Upstream has no heartbeat method; the deadman is the age of the last `robot.move`
(500 ms, `docs/upstream-notes.md`). A walking step therefore resends `robot.move` every tick
even when the command is zero (person lost → hold still). The `Watchdog` runs in its own
task: if the executor stops ticking for 350 ms while it was driving, it calls
`backend.stop()` and says so in the log. Tests: `tests/executor/test_watchdog.py`.

## Steering toward a person

`direction: toward_person` turns bearing into yaw rate (`vyaw = 1.5 · bearing`, clamped by
the manifest), slows forward speed while the bearing is large, and eases off inside 30 cm of
the target distance. `target_reached` is `person_distance ≤ distance` from the card.
Distance comes from the ToF column at the bearing, else from the marker's apparent width.

## Failure and refusal handling

| Gate says | Executor does |
| --- | --- |
| `battery_low`, `unknown_param` | fail the behavior, stop the duck |
| `precondition_failed`, `no_health_snapshot` | wait up to 5 s (transitions such as `rise`), then fail |
| `rate_limited` | try again next tick |
| `BehaviorRefused` from the robot | fail the step with the robot's reason |
| connection lost | fail, stop, log "Verbindung zur Ente verloren" |

## Speech in v1

`POST /api/say` is the Studio's „Ich sage: …“ button (`CLAUDE.md` §9). Idle: a phrase that
matches a pack's `trigger.phrases.de` starts it. Running: the phrase feeds `until: speech`
conditions for one tick. Real speech recognition is a later backend for the same call.
