# ADR-0011: Behaviors drafted from a sentence — the model drafts, the person decides

- Status: accepted
- Date: 2026-09-24

## Context

`CLAUDE.md` §4 says the planner — goal in, skill graph out, by an LLM — is Phase 2, and that in
v1 the person builds the behavior in the Studio. M3 measured that path: 21 s from an empty card
to a running behavior for someone who knows the Studio. For someone who does not, the first
behavior is the hard part, and §3.1 is about exactly that person.

ADR-0009 put vendor keys into the Studio. A text model with those keys can turn „Wenn ich
‚Hallo‘ sage, such mich, lauf zu mir und quak zweimal" into a behavior pack in seconds — but a
planner that also *runs* what it planned is the Phase-2 decision, with safety questions this
repository has not answered.

## Decision

1. **A draft, never a run.** „Mit KI entwerfen" on the overview sends the sentence to the
   chosen vendor's text model and opens the answer in the editor as a draft — the same path a
   file or a copy takes. Nothing is saved or started until the person presses Speichern and
   Start. The notice says whose draft it is and to read every step.
2. **Checked like any pack.** The answer is parsed as JSON and validated against
   `duckstudio.behavior/v0` and the skill registry. A draft that fails gets one more try with
   the problems listed; after that the Studio says it did not work. A taken id is renamed.
   Every safety check in the executor applies to a drafted behavior as to any other.
3. **The model sees the catalogue, not the duck.** The prompt carries the building blocks
   (ids, names, card controls and their options), the rules of the format, and two example
   packs. No camera frame is sent. Model output is data (§10): parsed, validated, never
   followed as an instruction.
4. **Text models per vendor**, chosen for structure rather than vision: `gemini-3.8-flash`,
   `claude-opus-5` (official SDK, server-side `fallbacks: "default"` so a declined request is
   answered by the model Anthropic recommends), `gpt-6-sol` (`store: false`). Keys and their
   handling are ADR-0009's.
5. **§4 stands.** This is not the Phase-2 planner: no goal decomposition at run time, no
   behavior the person has not read. It is the editor with a first draft filled in.

## Alternatives considered

- **Wait for Phase 2.** The keys, the schema and the validation exist now; the draft path adds
  nothing the person cannot already do by hand, and removes the blank page.
- **Let the model run the behavior directly.** That is the planner, and it needs its own safety
  design (who stops a plan the person never read?). Not in v1.
- **Structured output with the full JSON Schema.** The pack schema uses unions and patterns
  that vendors' schema dialects handle differently; JSON mode plus our own validation and one
  retry behaves the same on all three.
- **Templates only.** They help the first minute; they do not help „…und quak zweimal".

## Consequences

- The first behavior can start from a sentence; the editor, the cards and the file view teach
  the rest.
- A draft can be wrong in ways validation cannot see (a walk toward the wrong thing, an `until`
  that never ends). The notice asks the person to read it; the executor's limits (clamps,
  battery, deadman, `always` rules, Notstopp) are unchanged.
- Drafting has not been run against a real vendor answer yet (no key at hand); the flow was
  checked end to end with a scripted model and, live, up to a real vendor's rejection of a
  made-up key.
