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

A step's `only_if: {ask: …}` (ADR-0012) publishes a question of kind `check` instead: the
service frames it as yes/no (`check_prompt`, `found` = yes), stores the answer and no
sighting. An answer that comes back after its question was withdrawn is dropped, so a slow
model cannot decide the next step with the last one's picture.

The behavior names the vendor (its consent, ADR-0004); the router answers with that vendor
if a key for it is there, else with the stub (ADR-0009):

| Vendor | Provider | Key from | Frames leave the machine |
| --- | --- | --- | --- |
| — (no key) | `StubVlm` — the local blob detector in a VLM's clothes | — | no |
| `google` | `GeminiVlm` — Gemini, points as `[y, x]` in 0–1000 | Studio, or `GEMINI_API_KEY` + `DUCKSTUDIO_VLM=google` | yes, for behaviors that name it |
| `anthropic` | `AnthropicVlm` — Claude, official SDK | Studio, or `ANTHROPIC_API_KEY` + `DUCKSTUDIO_VLM=anthropic` | yes, for behaviors that name it |
| `openai` | `OpenAiVlm` — Responses API, `store: false` | Studio, or `OPENAI_API_KEY` + `DUCKSTUDIO_VLM=openai` | yes, for behaviors that name it |

The model per vendor is picked on the „KI-Anbieter" page (kept in `~/.config/duckstudio/ai.json`).
`DUCKSTUDIO_VLM_HZ` (default 0.5, clamped to 2.0). Each run may ask 200 questions, then the
service stops and says so.

## Old answers, steered by now

A model answers a second or two after the frame; even the local detector is 100–200 ms behind.
Every sighting carries `seen_from` — the duck's odometry (x, y, heading) as the frame was
taken — and `Snapshot.subject` hands the executor the sighting *as seen from where the duck is
now*: turned 20° left since means the thing is 20° further right, walked 50 cm towards it means
50 cm closer. Steering and `target_reached` both read that, so a slow answer neither makes the
duck overshoot its turn nor walk past the stop distance. Without odometry nothing changes;
without a range only the turn is made up for (`perception/base.py::Sighting.seen_now`).

## What the log says

Every question that leaves the machine is announced once — "Bild wird an Anthropic
gesendet: „Wo ist der rote Ball?“" — and every answer that differs from the last one is a
line of its own. A provider the behavior did not name is refused in the log, in red, and no
frame is sent (§7). The Live panel shows the same in a red band while a behavior is asking.

## Writing another detector

Anything with `detect(frame, timestamp) -> PersonDetection | None` plugs into the person
slot (`MagentaPersonDetector` for the sim marker, `MockBarDetector` for the mock backend, a
real detector later). Anything with `look(frame, question) -> VlmAnswer` plus `name`,
`model`, `configured` and `sends_frames` plugs into the VLM slot. Both are exercised by
`runtime/tests/executor/test_vlm.py` and `runtime/tests/safety/test_vlm_optin.py`.
