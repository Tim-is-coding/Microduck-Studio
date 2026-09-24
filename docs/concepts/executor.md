# Executor

`runtime/duckstudio/executor/tree.py` runs a behavior pack as a vertical step list with side
branches (`CLAUDE.md` §3.2, §6.4). No general behaviour-tree library: the shape is fixed
(trigger → steps → always-rules) and every branch hangs off a step.

## One tick, 10 Hz

1. Refresh the step context in the shared `Snapshot` (`now`, `elapsed_s`, `budget_s`,
   `stop_distance_m`, `steering`). Perception writes into the same object at its own rates;
   the tick never waits for it.
2. **Gamepad preemption**: any `pad.report` frame with events → `robot.stop`, state
   `preempted`, nothing else goes out. Authority order (§4) is e-stop > gamepad > executor.
3. **`always` rules** are evaluated before the active node. When one fires
   (`on: fallen`), its actions run in order: skill ids as one-shot skill runs, then a reserved
   word — `resume` returns to the interrupted step, `abort` fails the behavior, `stop` halts.
   A rule that fires more than three times in a row fails the behavior ("Erholung klappt
   nicht"). An action refused for a precondition (getup while already standing) is skipped.
   `getup` ends on `steady` — upright (≤ ~26°) without a break for 2 s — not on the first
   tick the duck is off the floor: the neck uncurls last, and a step resumed before that
   reads the floor as an obstacle (measured in duck-sim, `docs/upstream-notes.md`).
4. **The active step**:
   - `perceive: person.nearest` succeeds when a fresh detection (< 1 s) exists;
     `perceive: vlm.target` when a fresh VLM sighting (< 6 s) does — the step publishes its
     question, the perception service asks it (ADR-0004), the tick only reads the answer.
     `on_none` runs its skill for `seconds` (look_around sweeps the head), then
     `retry` / `abort` / `continue`.
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

## Steering toward something

`direction: toward_person` and `direction: toward_target` share one function
(`steer_toward`): bearing becomes yaw rate (`vyaw = 1.5 · bearing`, clamped by the
manifest), forward speed drops while the bearing is large, and eases off inside 30 cm of the
distance the card asked for. `target_reached` compares that distance against whichever
sighting the step steers by (`snapshot.steering`). Range comes from the ToF zone the thing
appears in, else — for the local detector — from the marker's apparent width.

With nothing fresh to steer by, the step sends a zero `robot.move` every tick: the duck
stands still and the deadman stays fed.

## Failure and refusal handling

| Gate says | Executor does |
| --- | --- |
| `battery_low`, `unknown_param` | fail the behavior, stop the duck |
| `precondition_failed`, `no_health_snapshot` | wait up to 5 s (transitions such as `rise`), then fail |
| `rate_limited` | try again next tick |
| `BehaviorRefused` from the robot | fail the step with the robot's reason |
| connection lost | fail, stop, log "Verbindung zur Ente verloren" |

## Speech

`POST /api/say` takes what the Studio heard: typed, clicked, or spoken into the microphone and
recognised in the browser (ADR-0008 — the runtime only ever gets text). Idle: a pack whose
`trigger.phrases` (any language) appear in what was heard starts; the longest match wins.
Running: the text feeds `until: speech` conditions for one tick. A phrase matches when its words
appear in order, as whole words (`phrase_in`): „Okay, folge mir bitte“ starts „Folge mir“,
„Stoppuhr“ is not „Stopp“. The duck's own microphone will be a second source for the same call.

## What a run leaves behind

A run nobody can look back at is hard to trust, so the executor keeps the last ten
(`RunRecord`, `HISTORY_DEPTH`): which behavior, when it started, how long it took, how it
ended, how far it got, and the reason in both languages. `GET /api/runs` serves them newest
first, and the Studio lists them under „Letzte Läufe“; the list is reloaded when a run
leaves `running`, not polled.

The record is written in the four places a run can end — done, failed, aborted, preempted —
and nowhere else, so a run that never started leaves no trace. The duration comes from the
monotonic clock (a clock change cannot bend it), the timestamp from the wall clock, because
the Studio prints it next to the log.
