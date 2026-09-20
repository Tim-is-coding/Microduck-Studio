# Perception

Two clocks (`CLAUDE.md` §4). Local detectors run on every camera frame and answer in
milliseconds; a VLM answers in a second or two, twice a minute. Both write into one
`Snapshot` that the executor reads last-value-wins and never waits for (§6.4).

```
backend.frame()  →  person detector   →  snapshot.person   5 Hz     local, free
backend.tof()    →                       snapshot.tof_*    sensor   local, free
backend.state()  →                       snapshot.state    10 Hz    local, free
backend.frame()  →  VLM provider      →  snapshot.target   0.5 Hz   ADR-0004, opt-in, paid
```

`runtime/duckstudio/perception/service.py` runs one asyncio task per row. Each survives a
backend that comes and goes, and none of them can block the executor's tick.

## Sightings

`PersonDetection` and `TargetSighting` are the same `Sighting`: a bearing (positive = left,
like `robot.move` `vyaw`), a range when a source agreed with it, and where the thing sat in
the image. The executor steers by whichever the step asked for, with the same maths
(`steer_toward`): turn towards it, slow down while turning, ease off as the gap closes.

Freshness differs because the clocks differ: a person detection counts as current for 1 s, a
VLM sighting for 6 s — three missed answers at 0.5 Hz, because nothing else is going to
refresh it sooner.

## Asking a model (ADR-0004)

A `perceive: vlm.target` step carries the question in the user's words:

```yaml
- perceive: vlm.target
  question: { de: "Wo ist der rote Ball?" }
  on_none: { do: look_around, seconds: 5, then: retry }
```

The executor publishes it as a *standing question* (`snapshot.vlm_request`) and reads
answers; the service asks. The question stands while a following `direction: toward_target`
walk needs fresh bearings, and is withdrawn — with the sighting — when the behavior ends,
is aborted or preempted, or when another perceive step takes over.

The provider is chosen by the runtime, the consent by the behavior:

| `DUCKSTUDIO_VLM` | Provider | Frames leave the machine |
| --- | --- | --- |
| unset (default) | `StubVlm` — the local blob detector in a VLM's clothes | no |
| `anthropic` | `AnthropicVlm` — Claude, needs `ANTHROPIC_API_KEY` and `uv sync --extra vlm` | yes, for behaviors that opted in |

Knobs: `DUCKSTUDIO_VLM_MODEL` (default `claude-opus-5`), `DUCKSTUDIO_VLM_HZ` (default 0.5,
clamped to 2.0). Each run may ask 200 questions, then the service stops and says so.

## What the log says

Every question that leaves the machine is announced once — "Bild wird an „anthropic“
gesendet: „Wo ist der rote Ball?“" — and every answer that differs from the last one is a
line of its own. A provider the behavior did not name is refused in the log, in red, and no
frame is sent (§7). The Live panel shows the same in a red band while a behavior is asking.

## Writing another detector

Anything with `detect(frame, timestamp) -> PersonDetection | None` plugs into the person
slot (`MagentaPersonDetector` for the sim marker, `MockBarDetector` for the mock backend, a
real detector later). Anything with `look(frame, question) -> VlmAnswer` plus `name`,
`model`, `configured` and `sends_frames` plugs into the VLM slot. Both are exercised by
`runtime/tests/executor/test_vlm.py` and `runtime/tests/safety/test_vlm_optin.py`.
