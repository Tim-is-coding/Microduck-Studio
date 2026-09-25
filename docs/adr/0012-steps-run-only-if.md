# ADR-0012: A step can run „nur wenn …" — a side branch, not a graph

- Status: accepted
- Date: 2026-09-25

## Context

`CLAUDE.md` §3.2 fixes the shape of a behavior: a vertical step list with side branches for a
condition and for an interrupt. Interrupts exist (`always`), and so does one special condition
(`on_none`: what to do when a perception step finds nothing). A general condition did not:
„quak nur, wenn jemand da ist", „lauf los, wenn vorne frei ist", „geh zum Ball, wenn er auf
dem Boden liegt" could not be built. The only way around was a second behavior.

The step list must stay a list: no free graph (§3.2), and nothing a person without a terminal
cannot read top to bottom (§3.1).

## Decision

1. **`only_if` on any step.** Skill, perceive and wait steps take an optional
   `only_if`. When the step is next, the check is settled first; yes runs the step, no skips
   it and the log says why („Schritt 2 übersprungen: nur wenn jemand zu sehen ist."). There is
   no `else` and no jump: skipping is the only branch, so the route stays a list.
2. **Two kinds of check.**
   - `{signal: "person_found"}` — the existing condition language (`tof_distance < 0.5`,
     `battery > 0.3`, `person_found == 0`), limited to what the duck and its sensors say right
     now. Signals that only mean something inside a running step (`timeout`, `elapsed`,
     `target_reached`) are refused by the schema, and so is an unknown name: it would never be
     true and the step would be skipped every time without a word. A signal nobody has
     reported yet gets 2 s, then the step is skipped with „nicht zu sagen, ob …".
   - `{ask: {de, en}, expect: yes|no}` — a yes/no question to the model the behavior opted
     into. It is a VLM use like `vlm.target`: it needs the `vlm:` opt-in (§7), the Studio shows
     the red line, the provider check in the perception service applies. The executor waits up
     to 12 s for an answer to a frame taken after the question was put, then skips with a
     warning. An answer to an earlier question never counts.
3. **One answer shape for every vendor.** The yes/no question is framed so that `found`
   carries the yes (`perception/vlm.py`, `check_prompt`). Claude, Gemini, OpenAI and the local
   stub answer it with the schema they already have; a check never leaves a target to steer at.
   A target asked for by an earlier step is set aside during the check and put back afterwards,
   so a `toward_target` walk behind a check still steers.
4. **In the Studio as sentences.** The card offers fixed choices — „jemand zu sehen ist",
   „niemand zu sehen ist", „ein Hindernis näher ist als … cm", „vorne frei ist, mindestens …
   cm", „der Akku mehr hat als … %", „die KI ja/nein sagt auf …". A signal written by hand in
   YAML that none of them expresses is shown and kept, not rewritten. A skipped step shows
   „übersprungen" in the run; a step still checking shows „prüft".

## Alternatives considered

- **`if`/`else` with nested step lists.** Expressive, and the first step towards the free
  graph §3.2 rules out; a nested list is also where people without a terminal get lost.
- **Jumps („weiter bei Schritt 4").** The same graph, with the edges hidden in numbers.
- **A separate yes/no schema per vendor.** Three more prompt/schema pairs to keep in step for
  what one boolean already says.
- **Checks only at the start of a behavior.** Most requests put the condition in the middle
  („such mich, und wenn du mich siehst, quak").

## Consequences

- Behaviors can react to the scene without a second behavior; the planner (ADR-0011) may use
  `only_if` when a request says „wenn".
- A skipped step counts as passed in „Letzte Läufe"; the log line is where the reason lives.
- Yes/no answers from real vendors are not checked live yet (same as ADR-0009); the stub
  answers yes when it sees its marker and no otherwise.
