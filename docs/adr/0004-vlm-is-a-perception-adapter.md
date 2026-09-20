# ADR-0004: The VLM is a perception adapter, opt-in per behavior, never in the loop

- Status: accepted
- Date: 2026-09-20

## Context

`CLAUDE.md` §9 left the question open: which VLM answers "where is the thing" for Phase 2,
and how is it wired so the model stays swappable? Two constraints are already fixed. §4
gives perception two clock rates — local detectors at 10–30 Hz, a VLM at 0.5–2 Hz that may
never sit in the loop that brakes the duck. §7 says camera frames leave the runtime only to
the user's Studio unless a behavior opts in, and the Studio marks it.

Until now the Studio had the opt-in switch (`vlm: { provider: … }`, with the red warning)
and the runtime did nothing with it — a control that promised something nothing delivered.
The walk skill likewise offered `direction: toward_target` with nothing producing a target.

Checked against the current API (2026-09-20, `anthropic` 1.7.0): images go to
`POST /v1/messages` as a base64 `image` content block; `output_config.format` with a JSON
Schema pins the answer shape; `output_config.effort` trades latency against thoroughness.
A 360×640 frame is ≈300 input tokens, so one question costs well under a cent on
`claude-opus-5` ($5/$25 per MTok) — but 0.5 Hz for ten minutes is 300 questions, which is
why the budget below exists.

## Decision

1. **A provider protocol, not a model.** `runtime/duckstudio/perception/vlm.py` defines
   `VlmProvider`: `look(frame, question) -> VlmAnswer`, plus `name`, `model`, `configured`
   and `sends_frames`. Swapping the model means swapping the class; nothing else in the
   runtime knows what answered.
2. **Two providers ship.** `AnthropicVlm` (Claude through the official SDK, default model
   `claude-opus-5`, `effort: low`, structured JSON output, `DUCKSTUDIO_VLM_MODEL` to change
   it) and `StubVlm`, which answers from the local blob detector so the Studio, the editor
   and the executor work with no key, no network and no frame leaving the machine.
3. **The stub is the default.** `DUCKSTUDIO_VLM=anthropic` opts into the paid service.
   A key lying around in the environment is not consent to spend money on every frame.
4. **The question is a step, the answer is a snapshot value.** A `perceive: vlm.target` step
   carries `question: { de: … }`. The executor publishes it as a standing question; the
   perception service asks it in its own task at 0.5 Hz (`DUCKSTUDIO_VLM_HZ`, clamped to
   2 Hz) and writes `snapshot.target`. The executor only ever reads the last answer — the
   tick never waits for a model (§6.4).
5. **The question stands while the duck walks to the thing.** It is withdrawn when the
   behavior ends, when the run is aborted or preempted, or when another perceive step takes
   over — and the sighting goes with it. `direction: toward_target` steers by that sighting
   with the same maths as `toward_person`.
6. **Consent is checked where the frame is sent, by name.** The perception service refuses to
   hand a frame to a provider the behavior did not name (`vlm.provider_mismatch`, error) and
   to an unconfigured one (`vlm.not_configured`, warning). A provider that does not send
   frames anywhere may stand in, and says so (`vlm.stub_stands_in`). Every send is logged
   ("Bild wird an … gesendet"), once per question, not once per frame.
7. **A run has a call budget.** 200 questions per behavior run (`vlm_max_calls`), then the
   asking stops with a warning. Without a fresh sighting the walk holds still (and keeps its
   heartbeat), which is the same thing that happens when the thing is out of sight.

## Alternatives considered

- **Call the VLM from the executor tick.** Rejected: a second of latency inside a 10 Hz loop
  is a duck that keeps walking while it thinks (§4).
- **Let the model return a velocity or a skill.** Rejected: §3.6 keeps planning and execution
  apart — the model points, RL policies walk. It answers "where", never "how fast".
- **Send frames continuously and let behaviors read a running description.** Rejected: cost
  and §7 both want the narrowest possible path — one standing question, one answer, only
  while a behavior asks.
- **Ask the model for a bounding box.** Rejected for v1: a point is what §9 asked for
  ("Zielpixel"), and the ToF gives a better range than an apparent width ever will.
- **No opt-in, just a global setting.** Rejected: the behavior is what travels (Hub, M4), so
  the consent has to travel with it.

## Consequences

- A behavior that asks a model cannot be saved without the `vlm:` block — the schema refuses
  it, and the Studio turns the opt-in on when a step asks for it, with the red line visible.
- The Claude provider needs an extra: `uv sync --extra vlm`. Without it, `configured` is
  false, the runtime says so in the log and sends nothing.
- `claude-opus-5` is a deliberate default, not a cost-optimized one. Operators who want a
  cheaper or faster model set `DUCKSTUDIO_VLM_MODEL`; the adapter does not choose for them.
- Model answers are data, never instructions (§10): the runtime reads `found`, a pixel and a
  sentence for the log, and nothing else.
- A second query (`vlm.question`, answering yes/no about the scene) fits the same adapter;
  it is not built until a behavior needs it.
